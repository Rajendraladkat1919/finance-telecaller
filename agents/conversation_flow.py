import enum
import json
from dataclasses import dataclass, field


class ConversationStage(str, enum.Enum):
    greeting = "greeting"
    identity_verify = "identity_verify"
    loan_discovery = "loan_discovery"
    requirement_gathering = "requirement_gathering"
    eligibility_check = "eligibility_check"
    next_steps = "next_steps"
    closing = "closing"


@dataclass
class ConversationState:
    call_id: int
    customer_name: str
    customer_phone: str
    preferred_language: str = "en"
    stage: ConversationStage = ConversationStage.greeting
    messages: list[dict] = field(default_factory=list)

    # Gathered data
    identity_confirmed: bool = False
    loan_type: str | None = None
    loan_amount: float | None = None
    loan_purpose: str | None = None
    tenure_months: int | None = None
    has_collateral: bool | None = None
    interest_level: str | None = None  # high/medium/low
    wants_callback: bool = False
    opted_out: bool = False


def build_system_prompt(bank_name: str, language: str) -> str:
    lang_instruction = (
        "Respond in Hindi (Devanagari script). Use simple, polite language."
        if language == "hi"
        else "Respond in English. Use simple, polite, professional language."
    )

    return f"""You are Priya, a friendly telecaller agent for {bank_name}, a cooperative bank in India.
Your goal is to understand the customer's loan requirements and help them take the next step.

{lang_instruction}

## Your Personality
- Warm, patient, and professional
- Never pushy or aggressive
- Respect if the customer is busy or not interested
- Use the customer's name naturally in conversation

## Conversation Flow
Follow these stages in order:
1. GREETING: Introduce yourself and the bank. Confirm you're speaking to the right person.
2. IDENTITY_VERIFY: Politely confirm the customer's name.
3. LOAN_DISCOVERY: Ask if they have any loan requirements or financial needs.
4. REQUIREMENT_GATHERING: If interested, collect: loan type, amount needed, purpose, preferred tenure.
5. ELIGIBILITY_CHECK: Ask about monthly income and existing loans (to assess eligibility).
6. NEXT_STEPS: Offer to schedule a branch visit or send document checklist via WhatsApp/SMS.
7. CLOSING: Thank the customer. Confirm next steps.

## Key Rules
- If customer says "DND", "remove my number", or "not interested" firmly → acknowledge, apologize for inconvenience, and end politely.
- If customer asks to call back later → note preferred time and end call.
- Never promise specific interest rates or guaranteed approvals.
- Maximum call duration: ~5 minutes. Be concise.
- After each response, append a JSON block on a new line with this exact format:
  AGENT_DATA: {{"stage": "<current_stage>", "loan_type": null, "loan_amount": null, "loan_purpose": null, "tenure_months": null, "interest_level": null, "opted_out": false, "wants_callback": false}}
  Update the JSON fields as you gather information. Use null for unknown fields.

## Loan Products Available
- Home Loan (up to ₹50 lakhs, 20 years)
- Personal Loan (up to ₹5 lakhs, 5 years)
- Business/MSME Loan (up to ₹25 lakhs)
- Agriculture Loan (Kisan Credit Card, seasonal)
- Gold Loan (instant, up to ₹10 lakhs)
- Vehicle Loan (two-wheeler & four-wheeler)
- Education Loan (up to ₹15 lakhs)
"""


def extract_loan_data(messages: list[dict]) -> dict:
    """Parse AGENT_DATA JSON blocks from the last assistant message."""
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if "AGENT_DATA:" in content:
            try:
                json_str = content.split("AGENT_DATA:")[-1].strip()
                # Handle multiline or trailing text
                json_str = json_str.split("\n")[0].strip()
                return json.loads(json_str)
            except (json.JSONDecodeError, IndexError):
                pass
    return {}
