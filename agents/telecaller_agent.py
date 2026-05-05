import re

import anthropic

from agents.conversation_flow import (
    ConversationStage,
    ConversationState,
    build_system_prompt,
    extract_loan_data,
)
from config import settings


class TelecallerAgent:
    """Claude-powered telecaller that conducts loan discovery conversations."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-6"

    def get_opening_message(self, state: ConversationState, bank_name: str) -> str:
        """Generate the first message the agent speaks when the call connects."""
        if state.preferred_language == "hi":
            return (
                f"नमस्ते! क्या मैं {state.customer_name} जी से बात कर सकती हूँ? "
                f"मैं Priya बोल रही हूँ, {bank_name} से।"
            )
        return (
            f"Hello! May I please speak with {state.customer_name}? "
            f"This is Priya calling from {bank_name}."
        )

    def reply(self, state: ConversationState, customer_input: str) -> str:
        """
        Given the customer's last spoken input, generate the agent's next response.
        Updates state.messages in place and returns the text to speak.
        """
        state.messages.append({"role": "user", "content": customer_input})

        system = build_system_prompt(settings.bank_name, state.preferred_language)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=system,
            messages=state.messages,
        )

        assistant_text = response.content[0].text
        state.messages.append({"role": "assistant", "content": assistant_text})

        # Update conversation state from embedded JSON
        data = extract_loan_data(state.messages)
        if data:
            if data.get("stage"):
                try:
                    state.stage = ConversationStage(data["stage"])
                except ValueError:
                    pass
            state.loan_type = data.get("loan_type") or state.loan_type
            state.loan_amount = data.get("loan_amount") or state.loan_amount
            state.loan_purpose = data.get("loan_purpose") or state.loan_purpose
            state.tenure_months = data.get("tenure_months") or state.tenure_months
            state.interest_level = data.get("interest_level") or state.interest_level
            state.opted_out = data.get("opted_out", False)
            state.wants_callback = data.get("wants_callback", False)

        # Return only the spoken text — strip the AGENT_DATA block
        spoken = self._strip_agent_data(assistant_text)
        return spoken

    def summarize_call(self, state: ConversationState) -> str:
        """Generate a structured summary of the call for bank staff."""
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in state.messages
        )
        prompt = f"""Summarize this loan call in 3-4 sentences for bank staff.
Include: customer interest level, loan type & amount mentioned, any concerns, recommended next action.

TRANSCRIPT:
{transcript}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _strip_agent_data(self, text: str) -> str:
        """Remove the AGENT_DATA JSON block from spoken text."""
        lines = text.split("\n")
        spoken_lines = [l for l in lines if not l.strip().startswith("AGENT_DATA:")]
        return "\n".join(spoken_lines).strip()
