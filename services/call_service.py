"""
Handles outbound call initiation via Twilio and retry scheduling.
"""

from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.rest import Client as TwilioClient

from config import settings
from models.call import Call, CallStatus
from models.customer import Customer, CustomerStatus


def _twilio_client() -> TwilioClient:
    return TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)


def _is_calling_hours() -> bool:
    """Returns True if current IST time is within allowed calling window."""
    # Simple UTC+5:30 offset check (production: use pytz or zoneinfo)
    now_utc = datetime.now(timezone.utc)
    ist_hour = (now_utc.hour + 5) % 24 + (1 if now_utc.minute >= 30 else 0)
    return settings.call_start_hour <= ist_hour < settings.call_end_hour


class CallService:

    @staticmethod
    async def initiate_call(db: AsyncSession, customer: Customer) -> Call | None:
        """Place an outbound call to the customer via Twilio."""
        if not _is_calling_hours():
            return None

        # Count previous attempts
        result = await db.execute(
            select(func.count()).where(Call.customer_id == customer.id)
        )
        attempts = result.scalar() or 0
        if attempts >= settings.max_call_attempts:
            return None

        # Create call record first so webhook can find it
        call = Call(
            customer_id=customer.id,
            status=CallStatus.scheduled,
            attempt_number=attempts + 1,
        )
        db.add(call)
        await db.flush()  # get call.id

        try:
            twilio = _twilio_client()
            twilio_call = twilio.calls.create(
                to=customer.phone,
                from_=settings.twilio_phone_number,
                url=f"{settings.public_base_url}/voice/answer",
                status_callback=f"{settings.public_base_url}/voice/status",
                status_callback_method="POST",
                timeout=30,
            )
            call.twilio_call_sid = twilio_call.sid
            await db.commit()
            return call
        except Exception as e:
            call.status = CallStatus.failed
            await db.commit()
            raise

    @staticmethod
    async def get_recent_calls(db: AsyncSession, limit: int = 50) -> list[Call]:
        result = await db.execute(
            select(Call)
            .order_by(Call.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_call_stats(db: AsyncSession) -> dict:
        total = await db.scalar(select(func.count()).select_from(Call))
        completed = await db.scalar(
            select(func.count()).where(Call.status == CallStatus.completed)
        )
        no_answer = await db.scalar(
            select(func.count()).where(Call.status == CallStatus.no_answer)
        )
        return {
            "total": total or 0,
            "completed": completed or 0,
            "no_answer": no_answer or 0,
            "success_rate": round((completed / total * 100) if total else 0, 1),
        }

    @staticmethod
    async def run_daily_campaign(db: AsyncSession) -> int:
        """Trigger calls for all active customers. Called by scheduler."""
        result = await db.execute(
            select(Customer).where(Customer.status == CustomerStatus.active)
        )
        customers = list(result.scalars().all())
        initiated = 0
        for customer in customers:
            try:
                call = await CallService.initiate_call(db, customer)
                if call:
                    initiated += 1
            except Exception:
                pass
        return initiated
