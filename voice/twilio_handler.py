"""
Twilio webhook handlers. Twilio calls these URLs during a live call.

Flow:
  1. POST /voice/answer   → called when customer picks up  → returns TwiML <Gather>
  2. POST /voice/gather   → called with customer's speech  → agent replies → <Gather> again
  3. POST /voice/status   → called when call ends          → update DB
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

from agents.conversation_flow import ConversationState
from agents.telecaller_agent import TelecallerAgent
from config import settings
from database import get_db
from models.call import Call, CallStatus, LoanRequirement
from models.customer import Customer

router = APIRouter(prefix="/voice", tags=["voice"])

# In-memory store of active call states. For production: use Redis.
_call_states: dict[str, ConversationState] = {}
_agent = TelecallerAgent()

VOICE_LANGUAGE = {"en": "en-IN", "hi": "hi-IN"}
VOICE_NAME = {"en": "Polly.Aditi", "hi": "Polly.Aditi"}  # AWS Polly via Twilio


def _twiml_speak(text: str, lang: str = "en") -> VoiceResponse:
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        language=VOICE_LANGUAGE.get(lang, "en-IN"),
        speech_timeout="auto",
        action=f"{settings.public_base_url}/voice/gather",
        method="POST",
    )
    gather.say(text, voice=VOICE_NAME.get(lang, "Polly.Aditi"), language=VOICE_LANGUAGE.get(lang, "en-IN"))
    resp.append(gather)
    # If no speech detected, re-prompt once
    resp.say("I didn't catch that. Please call us back at your convenience. Thank you!", language="en-IN")
    resp.hangup()
    return resp


@router.post("/answer")
async def call_answer(
    request: Request,
    CallSid: str = Form(...),
    To: str = Form(...),
    From: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Twilio calls this when the customer answers."""
    # Find the call record by Twilio SID (set earlier when call was initiated)
    result = await db.execute(select(Call).where(Call.twilio_call_sid == CallSid))
    call = result.scalar_one_or_none()

    if not call:
        # Fallback: phone number lookup
        customer_result = await db.execute(
            select(Customer).where(Customer.phone == From)
        )
        customer = customer_result.scalar_one_or_none()
        if not customer:
            vr = VoiceResponse()
            vr.say("Sorry, we could not process your call. Goodbye.")
            vr.hangup()
            return Response(str(vr), media_type="application/xml")
    else:
        customer_result = await db.execute(
            select(Customer).where(Customer.id == call.customer_id)
        )
        customer = customer_result.scalar_one_or_none()

    # Update call status
    if call:
        call.status = CallStatus.in_progress
        call.started_at = datetime.now(timezone.utc)
        await db.commit()

    lang = customer.preferred_language if customer else "en"
    state = ConversationState(
        call_id=call.id if call else 0,
        customer_name=customer.name if customer else "Customer",
        customer_phone=From,
        preferred_language=lang,
    )
    _call_states[CallSid] = state

    opening = _agent.get_opening_message(state, settings.bank_name)
    return Response(str(_twiml_speak(opening, lang)), media_type="application/xml")


@router.post("/gather")
async def call_gather(
    request: Request,
    CallSid: str = Form(...),
    SpeechResult: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Twilio calls this with the customer's transcribed speech."""
    state = _call_states.get(CallSid)
    if not state:
        vr = VoiceResponse()
        vr.say("Thank you for calling. Goodbye.")
        vr.hangup()
        return Response(str(vr), media_type="application/xml")

    customer_input = SpeechResult.strip()
    if not customer_input:
        customer_input = "[silence]"

    agent_reply = _agent.reply(state, customer_input)

    # Check end conditions
    if state.opted_out or state.stage.value == "closing":
        vr = VoiceResponse()
        vr.say(agent_reply, voice=VOICE_NAME.get(state.preferred_language, "Polly.Aditi"),
               language=VOICE_LANGUAGE.get(state.preferred_language, "en-IN"))
        vr.hangup()
        await _finalize_call(CallSid, state, db)
        return Response(str(vr), media_type="application/xml")

    return Response(str(_twiml_speak(agent_reply, state.preferred_language)), media_type="application/xml")


@router.post("/status")
async def call_status(
    request: Request,
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: str = Form(default="0"),
    db: AsyncSession = Depends(get_db),
):
    """Twilio posts status updates here (completed, no-answer, busy, failed)."""
    state = _call_states.pop(CallSid, None)

    result = await db.execute(select(Call).where(Call.twilio_call_sid == CallSid))
    call = result.scalar_one_or_none()
    if not call:
        return Response("ok")

    status_map = {
        "completed": CallStatus.completed,
        "no-answer": CallStatus.no_answer,
        "busy": CallStatus.busy,
        "failed": CallStatus.failed,
    }
    call.status = status_map.get(CallStatus.lower(), CallStatus.failed)
    call.ended_at = datetime.now(timezone.utc)
    call.duration_seconds = int(CallDuration)

    if state and state.messages:
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in state.messages
        )
        call.transcript = transcript
        call.agent_summary = _agent.summarize_call(state)

        # Save loan requirement if gathered
        if state.loan_type or state.loan_amount:
            lr = LoanRequirement(
                call_id=call.id,
                customer_id=call.customer_id,
                loan_type=state.loan_type,
                loan_amount=state.loan_amount,
                loan_purpose=state.loan_purpose,
                tenure_months=state.tenure_months,
                has_collateral=state.has_collateral,
                interest_level=state.interest_level,
                raw_notes=call.agent_summary,
            )
            db.add(lr)

    await db.commit()
    return Response("ok")


async def _finalize_call(call_sid: str, state: ConversationState, db: AsyncSession):
    """Persist call data immediately when conversation ends naturally."""
    result = await db.execute(select(Call).where(Call.twilio_call_sid == call_sid))
    call = result.scalar_one_or_none()
    if not call:
        return

    transcript = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in state.messages
    )
    call.transcript = transcript
    call.agent_summary = _agent.summarize_call(state)

    if state.loan_type or state.loan_amount:
        lr = LoanRequirement(
            call_id=call.id,
            customer_id=call.customer_id,
            loan_type=state.loan_type,
            loan_amount=state.loan_amount,
            loan_purpose=state.loan_purpose,
            tenure_months=state.tenure_months,
            has_collateral=state.has_collateral,
            interest_level=state.interest_level,
            raw_notes=call.agent_summary,
        )
        db.add(lr)

    await db.commit()
