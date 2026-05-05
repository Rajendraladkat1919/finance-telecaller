from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.customer import Customer, CustomerStatus


class CustomerService:

    @staticmethod
    async def create(db: AsyncSession, name: str, phone: str, **kwargs) -> Customer:
        customer = Customer(name=name, phone=phone, **kwargs)
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
        return customer

    @staticmethod
    async def get_by_phone(db: AsyncSession, phone: str) -> Customer | None:
        result = await db.execute(select(Customer).where(Customer.phone == phone))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_callable(db: AsyncSession) -> list[Customer]:
        """Return customers who can be called (active, not DND)."""
        result = await db.execute(
            select(Customer).where(Customer.status == CustomerStatus.active)
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_dnd(db: AsyncSession, customer_id: int):
        result = await db.execute(select(Customer).where(Customer.id == customer_id))
        customer = result.scalar_one_or_none()
        if customer:
            customer.status = CustomerStatus.dnd
            await db.commit()

    @staticmethod
    async def bulk_import(db: AsyncSession, rows: list[dict]) -> int:
        """Import customers from a list of dicts. Skips duplicates by phone."""
        count = 0
        for row in rows:
            existing = await CustomerService.get_by_phone(db, row["phone"])
            if not existing:
                db.add(Customer(**row))
                count += 1
        await db.commit()
        return count
