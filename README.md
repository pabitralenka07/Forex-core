# Forex-Core

Forex-Core is an asynchronous currency conversion and foreign exchange rate service built with FastAPI and Streamlit. It is engineered with high numerical accuracy, strict Decimal arithmetic, and multi-tier resilience.

---

## Architecture Overview

Forex-Core separates the application into a decoupled backend API and a Streamlit interactive frontend:

- **Frontend (Streamlit)**: Communicates exclusively with the FastAPI backend over HTTP JSON envelopes. Never connects directly to external exchange rate providers.
- **Backend (FastAPI)**: Implements ISO 4217 minor-unit rounding, Decimal calculation routines, thread-safe rate caching, provider failover mechanisms, database persistence, and API key rate limiting.
- **Upstream Providers**: Frankfurter (European Central Bank reference rates) as primary, with ExchangeRate-API as an automatic fallback adapter.

---

## Core Technical Features

### 1. Arbitrary-Precision Financial Math
- Floating-point representations (`float`) are completely forbidden for monetary amounts and exchange rates.
- All JSON numbers from providers are parsed directly into `decimal.Decimal`.
- Serialized output uses string-encoded decimals in JSON responses to prevent IEEE 754 precision loss on client runtimes.
- Rounding follows target currency minor units (e.g., JPY: 0, USD: 2, KWD: 3) using configurable rounding modes (`ROUND_HALF_UP` or `ROUND_HALF_EVEN`).

### 2. Multi-Provider Resilience & Caching
- **RateProvider Interface**: Decoupled provider abstraction allowing transparent addition of upstream feeds.
- **Circuit Breaker**: Individual circuit breaker tracking (`CLOSED`, `OPEN`, `HALF_OPEN`) per provider to guard against cascading failures.
- **In-Memory Cache & Coalescing**: Thread-safe TTL/LRU cache with single-flight request coalescing to eliminate duplicate outbound requests.
- **Stale Serving**: Transparent fallback to last-known good rates (`meta.stale = true`, `meta.age_seconds`) when all external providers fail.

### 3. Data Persistence & Analytics
- **Database Engine**: Asynchronous SQLAlchemy 2.x with explicit `Numeric(20, 10)` columns on SQLite.
- **Historical Analysis**: Statistical evaluation (minimum, maximum, average, and percentage change) calculated in Decimal over date ranges.
- **Audit Trails**: Conversion history recording with RFC 4180 streaming CSV export.
- **Favorites**: Per-session tracking of preferred currency pairs.

### 4. Security & Rate Limiting
- **API Key Management**: High-entropy keys prefixed with `ak_`, stored securely using SHA-256 digests.
- **SlowAPI Rate Limiter**: Multi-tier rate limiting supporting Free (60/min), Pro (300/min), and Enterprise (1200/min).
- **HTTP Security Headers**: Enforces HSTS, clickjacking prevention (`X-Frame-Options: DENY`), MIME sniffing protection (`X-Content-Type-Options: nosniff`), and strict Content Security Policy.

---

## API Endpoints

All responses follow a unified envelope (`success`, `data`, `meta`, `error`):

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Application liveness probe |
| `GET` | `/ready` | Database and provider connectivity probe |
| `GET` | `/v1/convert` | Forward currency conversion |
| `GET` | `/v1/convert/reverse` | Reverse currency conversion |
| `POST` | `/v1/convert/batch` | Batch conversion (one-to-many or pair list) |
| `GET` | `/v1/rates` | Latest rates for multiple symbols |
| `GET` | `/v1/rates/{base}/{target}` | Direct pair exchange rate |
| `GET` | `/v1/currencies` | ISO 4217 currency list and metadata |
| `GET` | `/v1/historical` | Historical single-date exchange rates |
| `GET` | `/v1/timeseries` | Historical range with min, max, avg, and % change |
| `GET` | `/v1/history` | Paginated conversion audit records |
| `GET` | `/v1/history/export` | RFC 4180 streaming CSV download |
| `POST` | `/v1/favorites` | Add currency to session favorites |
| `POST` | `/v1/auth/keys` | Generate a new tier-backed API key |
| `GET` | `/v1/auth/verify` | Inspect authenticated API key status |

---

## Local Setup & Execution

### 1. Environment Preparation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install streamlit plotly pandas slowapi
```

### 2. Running the FastAPI Server
```bash
PYTHONPATH=backend ./.venv/bin/uvicorn app.main:app --reload --port 8000
```
- Swagger UI Documentation: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/health`

### 3. Running the Streamlit UI
```bash
./.venv/bin/streamlit run frontend/app.py --server.port 8501
```
- Web Application: `http://localhost:8501`

### 4. Running the Test Suite
```bash
./.venv/bin/pytest backend/tests -v
./.venv/bin/ruff check backend frontend
(cd backend && ../.venv/bin/mypy app tests) && ./.venv/bin/mypy frontend
```
