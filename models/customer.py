import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class CustomerStatus(str, enum.Enum):
    active = "active"
    dnd = "dnd"          # Do Not Disturb - opted out
    converted = "converted"
    not_interested = "not_interested"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    preferred_language: Mapped[str] = mapped_column(String(10), default="en")  # en/hi
    city: Mapped[str | None] = mapped_column(String(50))
    occupation: Mapped[str | None] = mapped_column(String(100))
    monthly_income: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[CustomerStatus] = mapped_column(
        Enum(CustomerStatus), default=CustomerStatus.active
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    calls: Mapped[list["Call"]] = relationship("Call", back_populates="customer")
