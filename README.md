# PENTAGON5 ANGEL NIFTY TRIPLE ENGINE

Production-grade FastAPI application for NIFTY options trading via Angel One SmartAPI.

**Port:** 8056  
**Trading mode:** LIVE ONLY  
**Instruments:** NIFTY options (no futures, no other indices)

## Three Engines

| Engine | Default Allocation |
|--------|-------------------|
| Normal | 30% |
| Wick   | 30% |
| Ultra  | 40% |

Capital is auto-fetched from Angel available margin after login — no fixed capital.

## Session Schedule (IST)

| Time       | Phase                |
|------------|----------------------|
| 08:30:00   | Auto startup         |
| 09:00:00   | Pre-market analysis  |
| 09:07:31   | Bias lock            |
| 09:15:00   | Trading start        |
| 15:10:00   | Stop new entries     |
| 15:14:00   | Force exit all       |
| 15:30:00   | Next-day pre-watch   |
| 16:00:00   | Auto shutdown        |

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with Angel credentials

uvicorn app.main:app --host 0.0.0.0 --port 8056
```

Dashboard: http://localhost:8056  
Health: http://localhost:8056/api/v1/health  
Ready: http://localhost:8056/api/v1/ready

## Project Structure

```
app/
├── main.py              # FastAPI app factory
├── core/                # Config, logging, constants, state
├── api/v1/              # REST endpoints
├── broker/              # Angel SmartAPI integration
├── market/              # Instruments, candles, intelligence
├── engines/             # Normal, Wick, Ultra + adaptive controller
├── risk/                # Risk manager and locks
├── reports/             # Excel reports
├── storage/             # SQLite (PostgreSQL-ready)
└── models/              # Pydantic schemas and enums
```

## Milestone 1 Status

- [x] Full scaffold
- [x] FastAPI boot on port 8056
- [x] Dashboard (dark neon pink UI)
- [x] Health / readiness endpoints
- [x] Placeholder state API
- [ ] Angel login + WebSocket (next)
- [ ] Live order placement (next)
