"""REST API + HTML dashboard for bank staff."""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.call import Call, LoanRequirement
from models.customer import Customer
from services.call_service import CallService
from services.customer_service import CustomerService

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    name: str
    phone: str
    preferred_language: str = "en"
    city: str | None = None
    occupation: str | None = None
    monthly_income: int | None = None


class CallTriggerRequest(BaseModel):
    customer_id: int


# ── Customer endpoints ────────────────────────────────────────────────────────

@router.post("/customers", summary="Add a single customer")
async def add_customer(data: CustomerCreate, db: AsyncSession = Depends(get_db)):
    existing = await CustomerService.get_by_phone(db, data.phone)
    if existing:
        raise HTTPException(400, "Phone number already exists")
    customer = await CustomerService.create(db, **data.model_dump())
    return {"id": customer.id, "name": customer.name, "phone": customer.phone}


@router.post("/customers/import", summary="Bulk import customers from CSV")
async def import_customers(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """
    CSV must have columns: name, phone, preferred_language (optional), city (optional)
    """
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    rows = [row for row in reader]
    count = await CustomerService.bulk_import(db, rows)
    return {"imported": count, "total_in_file": len(rows)}


@router.get("/customers", summary="List all customers")
async def list_customers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer).order_by(Customer.created_at.desc()).limit(200))
    customers = result.scalars().all()
    return [
        {"id": c.id, "name": c.name, "phone": c.phone, "status": c.status,
         "city": c.city, "language": c.preferred_language}
        for c in customers
    ]


@router.delete("/customers/{customer_id}/dnd", summary="Mark customer as DND")
async def mark_dnd(customer_id: int, db: AsyncSession = Depends(get_db)):
    await CustomerService.mark_dnd(db, customer_id)
    return {"status": "marked_dnd"}


# ── Call endpoints ────────────────────────────────────────────────────────────

@router.post("/calls/trigger", summary="Manually trigger a call to a customer")
async def trigger_call(req: CallTriggerRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer).where(Customer.id == req.customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(404, "Customer not found")
    call = await CallService.initiate_call(db, customer)
    if not call:
        raise HTTPException(400, "Cannot initiate call (outside hours or max attempts reached)")
    return {"call_id": call.id, "twilio_sid": call.twilio_call_sid, "status": call.status}


@router.post("/calls/campaign", summary="Run outbound campaign for all active customers")
async def run_campaign(db: AsyncSession = Depends(get_db)):
    initiated = await CallService.run_daily_campaign(db)
    return {"calls_initiated": initiated}


@router.get("/calls", summary="List recent calls")
async def list_calls(db: AsyncSession = Depends(get_db)):
    calls = await CallService.get_recent_calls(db)
    return [
        {
            "id": c.id,
            "customer_id": c.customer_id,
            "status": c.status,
            "duration_seconds": c.duration_seconds,
            "attempt": c.attempt_number,
            "summary": c.agent_summary,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in calls
    ]


@router.get("/calls/{call_id}/transcript", summary="Get full call transcript")
async def get_transcript(call_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(404, "Call not found")
    return {"call_id": call_id, "transcript": call.transcript, "summary": call.agent_summary}


@router.get("/leads", summary="List gathered loan requirements")
async def list_leads(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LoanRequirement, Customer)
        .join(Customer, LoanRequirement.customer_id == Customer.id)
        .order_by(LoanRequirement.created_at.desc())
        .limit(100)
    )
    rows = result.all()
    return [
        {
            "id": lr.id,
            "customer": cust.name,
            "phone": cust.phone,
            "loan_type": lr.loan_type,
            "amount": lr.loan_amount,
            "purpose": lr.loan_purpose,
            "tenure_months": lr.tenure_months,
            "interest_level": lr.interest_level,
            "notes": lr.raw_notes,
            "date": lr.created_at.isoformat() if lr.created_at else None,
        }
        for lr, cust in rows
    ]


@router.get("/stats", summary="Dashboard statistics")
async def get_stats(db: AsyncSession = Depends(get_db)):
    stats = await CallService.get_call_stats(db)
    customer_result = await db.execute(select(Customer))
    stats["total_customers"] = len(customer_result.scalars().all())
    lead_result = await db.execute(select(LoanRequirement))
    stats["total_leads"] = len(lead_result.scalars().all())
    return stats


# ── HTML Dashboard ────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(db: AsyncSession = Depends(get_db)):
    stats = await CallService.get_call_stats(db)
    leads_result = await db.execute(
        select(LoanRequirement, Customer)
        .join(Customer, LoanRequirement.customer_id == Customer.id)
        .order_by(LoanRequirement.created_at.desc())
        .limit(20)
    )
    leads = leads_result.all()

    rows = ""
    for lr, cust in leads:
        rows += f"""
        <tr>
          <td>{cust.name}</td><td>{cust.phone}</td>
          <td>{lr.loan_type or '-'}</td>
          <td>{'₹{:,.0f}'.format(lr.loan_amount) if lr.loan_amount else '-'}</td>
          <td>{lr.interest_level or '-'}</td>
          <td>{lr.raw_notes[:80] + '...' if lr.raw_notes and len(lr.raw_notes) > 80 else lr.raw_notes or '-'}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Telecaller Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f4f6f9; color: #333; }}
    .header {{ background: #1a3c6e; color: white; padding: 16px 32px; }}
    .header h1 {{ margin: 0; font-size: 22px; }}
    .cards {{ display: flex; gap: 16px; padding: 24px 32px; flex-wrap: wrap; }}
    .card {{ background: white; border-radius: 8px; padding: 20px 28px; box-shadow: 0 1px 4px rgba(0,0,0,.1); min-width: 140px; }}
    .card .num {{ font-size: 32px; font-weight: bold; color: #1a3c6e; }}
    .card .label {{ font-size: 13px; color: #666; margin-top: 4px; }}
    .section {{ padding: 0 32px 32px; }}
    h2 {{ color: #1a3c6e; font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
    th {{ background: #1a3c6e; color: white; padding: 10px 14px; text-align: left; font-size: 13px; }}
    td {{ padding: 10px 14px; font-size: 13px; border-bottom: 1px solid #eee; }}
    tr:last-child td {{ border-bottom: none; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }}
    .high {{ background: #d4edda; color: #155724; }}
    .medium {{ background: #fff3cd; color: #856404; }}
    .low {{ background: #f8d7da; color: #721c24; }}
  </style>
</head>
<body>
  <div class="header"><h1>Telecaller Dashboard — Loan Campaign</h1></div>
  <div class="cards">
    <div class="card"><div class="num">{stats['total_customers']}</div><div class="label">Total Customers</div></div>
    <div class="card"><div class="num">{stats['total']}</div><div class="label">Calls Made</div></div>
    <div class="card"><div class="num">{stats['completed']}</div><div class="label">Completed Calls</div></div>
    <div class="card"><div class="num">{stats['success_rate']}%</div><div class="label">Connect Rate</div></div>
    <div class="card"><div class="num">{stats['total_leads']}</div><div class="label">Leads Generated</div></div>
  </div>
  <div class="section">
    <h2>Recent Loan Leads</h2>
    <table>
      <thead><tr><th>Customer</th><th>Phone</th><th>Loan Type</th><th>Amount</th><th>Interest</th><th>Summary</th></tr></thead>
      <tbody>{rows if rows else '<tr><td colspan="6" style="text-align:center;color:#999">No leads yet. Run a campaign to get started.</td></tr>'}</tbody>
    </table>
  </div>
  <div class="section">
    <h2>Quick Actions</h2>
    <p style="font-size:13px;color:#555">
      Use the REST API to trigger calls:<br>
      <code>POST /calls/campaign</code> — call all active customers<br>
      <code>POST /calls/trigger</code> — call a specific customer<br>
      <code>GET /leads</code> — export all loan leads (JSON)
    </p>
  </div>
</body>
</html>"""
