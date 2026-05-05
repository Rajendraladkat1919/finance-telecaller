"""
Finance Telecaller Agent — Entry Point

Start: uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from api.routes import router as api_router
from config import settings
from database import AsyncSessionLocal, init_db
from services.call_service import CallService
from voice.twilio_handler import router as twilio_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Schedule daily outbound campaign (Mon-Sat, 10 AM IST = 4:30 AM UTC)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_campaign_job,
        trigger="cron",
        day_of_week="mon-sat",
        hour=4,
        minute=30,
        timezone="UTC",
    )
    scheduler.start()

    yield

    scheduler.shutdown()


async def _run_campaign_job():
    async with AsyncSessionLocal() as db:
        count = await CallService.run_daily_campaign(db)
        print(f"[Scheduler] Daily campaign initiated {count} calls")


app = FastAPI(
    title="Finance Telecaller Agent",
    description="AI-powered loan telecaller for cooperative banks",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)
app.include_router(twilio_router)


@app.get("/health")
async def health():
    return {"status": "ok", "bank": settings.bank_name}
