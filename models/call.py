import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class CallStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    no_answer = "no_answer"
    busy = "busy"
    failed = "failed"
    callback_requested = "callback_requested"


class LoanType(str, enum.Enum):
    home = "home_loan"
    personal = "personal_loan"
    business = "business_loan"
    agriculture = "agriculture_loan"
    gold = "gold_loan"
    vehicle = "vehicle_loan"
    education = "education_loan"


class LoanRequirement(Base):
    __tablename__ = "loan_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))

    loan_type: Mapped[LoanType | None] = mapped_column(Enum(LoanType))
    loan_amount: Mapped[float | None] = mapped_column(Float)
    loan_purpose: Mapped[str | None] = mapped_column(String(200))
    tenure_months: Mapped[int | None] = mapped_column(Integer)
    has_collateral: Mapped[bool | None] = mapped_column(default=None)
    interest_level: Mapped[str | None] = mapped_column(String(20))  # high/medium/low
    raw_notes: Mapped[str | None] = mapped_column(Text)  # agent's extracted summary

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    call: Mapped["Call"] = relationship("Call", back_populates="loan_requirement")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    twilio_call_sid: Mapped[str | None] = mapped_column(String(50), unique=True)

    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus), default=CallStatus.scheduled
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    transcript: Mapped[str | None] = mapped_column(Text)
    agent_summary: Mapped[str | None] = mapped_column(Text)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    customer: Mapped["Customer"] = relationship("Customer", back_populates="calls")
    loan_requirement: Mapped[LoanRequirement | None] = relationship(
        "LoanRequirement", back_populates="call", uselist=False
    )
