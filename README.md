# Finance Telecaller Agent

AI-powered outbound telecaller for cooperative banks — calls customers, discovers loan requirements, and generates leads automatically.

## Architecture

```
Customer Phone
      ↕ (voice call)
   Twilio ──── webhooks ───→ FastAPI App
                                  │
                          Claude AI Agent  (conversation)
                                  │
                            SQLite DB      (leads, transcripts)
                                  │
                          Dashboard / REST API  (bank staff)
```

## Tech Stack

| Component | Technology | Cost |
|-----------|-----------|------|
| AI Agent | Claude Sonnet (Anthropic) | ~₹0.10–0.30 per call |
| Voice/Phone | Twilio Voice | ~₹3–5 per minute |
| Backend | FastAPI + Python | Free |
| Database | SQLite | Free |
| Scheduler | APScheduler | Free |

**Monthly estimate for 500 calls/month:** ~₹2,500–4,000

---

## Setup (Step by Step)

### 1. Prerequisites

- Python 3.11+
- Twilio account (twilio.com) — get a phone number
- Anthropic API key (console.anthropic.com)
- `ngrok` for local testing

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual keys
```

Key values to fill:
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` — from twilio.com/console
- `TWILIO_PHONE_NUMBER` — your Twilio India number (+91...)
- `PUBLIC_BASE_URL` — your public URL (use ngrok for dev)
- `BANK_NAME` — your bank's name

### 4. Expose localhost with ngrok (development)

```bash
ngrok http 8000
# Copy the https URL → paste into .env as PUBLIC_BASE_URL
```

### 5. Run the server

```bash
uvicorn main:app --reload --port 8000
```

### 6. Add customers and make first call

```bash
# Add a test customer
curl -X POST http://localhost:8000/customers \
  -H "Content-Type: application/json" \
  -d '{"name": "Ramesh Patil", "phone": "+919876543210", "preferred_language": "hi"}'

# Trigger a call manually
curl -X POST http://localhost:8000/calls/trigger \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1}'

# View dashboard
open http://localhost:8000/dashboard
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/customers` | Add a customer |
| POST | `/customers/import` | Bulk import from CSV |
| GET | `/customers` | List all customers |
| DELETE | `/customers/{id}/dnd` | Mark DND (opt-out) |
| POST | `/calls/trigger` | Call one customer now |
| POST | `/calls/campaign` | Call all active customers |
| GET | `/calls` | Recent call history |
| GET | `/calls/{id}/transcript` | Full transcript + AI summary |
| GET | `/leads` | All loan requirements gathered |
| GET | `/stats` | Dashboard statistics |
| GET | `/dashboard` | HTML dashboard |

---

## Bulk Import via CSV

Create a CSV file:

```csv
name,phone,preferred_language,city,occupation,monthly_income
Ramesh Patil,+919876543210,hi,Pune,Farmer,15000
Sunita Sharma,+919876543211,en,Nashik,Teacher,35000
```

```bash
curl -X POST http://localhost:8000/customers/import \
  -F "file=@customers.csv"
```

---

## How the Conversation Works

```
Agent: "Hello! May I speak with Ramesh Patil? This is Priya from ABC Bank."
Customer: "Haan, bol."
Agent: "Ramesh ji, we have some attractive loan offers. Do you have any loan needs?"
Customer: "Haan, mujhe business ke liye kuch paisa chahiye."
Agent: "Wonderful! Approximately how much do you need and for what purpose?"
Customer: "Around 5 lakh for shop expansion, 3 years."
Agent: "That's great. May I ask your monthly income to check eligibility?"
...
Agent: "I'll have our officer call you for a detailed discussion. Thank you!"
```

The agent:
- Speaks Hindi or English based on customer preference
- Extracts: loan type, amount, purpose, tenure, income
- Saves a structured summary for bank staff
- Respects DND requests immediately

---

## Small Cooperative Bank Integration Checklist

- [ ] Get Twilio India number (takes 1-2 days, requires business docs)
- [ ] Get Anthropic API key (instant)
- [ ] Deploy on a ₹500/month VPS (DigitalOcean/AWS Lightsail) or local PC
- [ ] Import your customer list via CSV
- [ ] Set BANK_NAME in .env
- [ ] Set call hours (default 9 AM – 6 PM IST)
- [ ] Train 1 staff member to use the dashboard
- [ ] Follow RBI telemarketing guidelines (register with TRAI DND portal)

---

## Production Deployment (Simple)

```bash
# Install on Ubuntu VPS
pip install -r requirements.txt
pip install gunicorn

# Run with gunicorn
gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Keep running (systemd service recommended)
```

For production, replace SQLite with PostgreSQL by changing `DATABASE_URL` to `postgresql+asyncpg://...`

---

## Compliance Notes (India)

1. Register your business number on TRAI's DLT platform
2. Get consent before calling (TRAI regulations)
3. Honor DND requests immediately — the system auto-marks opted-out customers
4. Call only between 9 AM – 9 PM (the system enforces 9 AM – 6 PM by default)
5. Inform customers they are speaking with an AI agent (best practice)
