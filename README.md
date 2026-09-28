# PayFlow — Payment & Transaction Management Platform

An educational full-stack payment processing and transaction ledger platform built with **Python (Flask)**, **SQLite**, and **vanilla HTML/CSS/JavaScript**.

> **Note on Scope:** This is an educational simulation. It does not move real money, connect to live bank rails, or collect sensitive cardholder information. It models the core architectural safeguards required in production fintech platforms: **idempotency keys**, **integer-based minor currency units (paise)**, **ACID transactions**, and **finite state machine validations**.

---

## 1. Key Engineering Highlights

| Concept | Why It Matters | Implementation in PayFlow |
| :--- | :--- | :--- |
| **Idempotency** | Prevents duplicate payments on double-clicks or network retries. | Client sends a unique `idempotency_key`. Exact retries return `200 OK` (replay); modified payloads with reused keys return `409 Conflict`. |
| **Integer Money** | Floating-point numbers (`float`) cause rounding bugs (`0.1 + 0.2 != 0.3`). | All amounts are validated and stored as positive integer **paise** (`₹1.00 = 100 paise`). Rupees are calculated only for display. |
| **ACID Transactions** | Refunds must not leave the ledger in a partially-updated state if a step fails. | The refund record insertion, payment status update, and audit log write execute in a single atomic database transaction (`with conn:`). |
| **State Machine Guard** | Prevents illegal state transitions (e.g. refunding a failed or pending payment). | State transitions are validated before writing. Only `succeeded` payments can be refunded, and exactly once. |
| **Audit Trail** | Financial platforms require non-repudiation and lifecycle history. | Every state transition is appended to an immutable `status_history` table with timestamps and notes. |

---

## 2. System Architecture & State Machine

```
Browser / Client (HTML, CSS, Vanilla JS)
        │
        ▼ HTTP REST (JSON)
Flask Application (app.py)
        │
        ▼ Validation & Business Rules
Services Layer (services.py)
        │
        ▼ Parameterized SQL + ACID Transactions
SQLite Database (instance/payflow.db)
```

### Payment Lifecycle Transitions
```
                [ Client Request ]
                        │
                        ▼
                    [ pending ]
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
       [ succeeded ]             [ failed ] (Terminal)
            │
            ▼ (POST /refund)
       [ refunded ] (Terminal)
```

---

## 3. Quickstart & Local Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.12)
- No external database engine or node/npm build tools required.

### 1. Clone & Install
```bash
git clone https://github.com/rouhan0trix/payflow.git
cd payflow

# Install Flask
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```
*(The SQLite database and tables will be initialized automatically in `instance/payflow.db` on first run).*

---

## 4. Running Automated Tests

PayFlow includes a comprehensive automated test suite built with Python's standard `unittest` framework:

```bash
python -m unittest discover tests -v
```

### Test Coverage Highlights:
- Valid payment creation (HTTP 201)
- Input boundary validation (negative, zero, decimal, string, and missing amounts -> HTTP 400)
- Idempotency replay verification (identical payload returns HTTP 200 without inserting duplicate)
- Idempotency key conflict detection (modified payload returns HTTP 409)
- Payment retrieval & 404 handling
- Successful refund lifecycle (HTTP 200, updates payment, creates refund row, logs audit trail)
- Refund state guards (refunding failed, pending, or already refunded payment returns HTTP 409)
- ACID database transaction rollback on error
- SQL injection defense (parameterized queries)
- Health check route (`/health`)

---

## 5. REST API Endpoints

| Method | Endpoint | Description | Expected Status |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/payments` | Create simulated payment | `201` (New), `200` (Replay), `400` (Invalid), `409` (Conflict) |
| `GET` | `/api/payments` | List payments (`status`, `search`, `limit`, `offset`) | `200 OK` |
| `GET` | `/api/payments/<id>` | Get payment details, refund, and history | `200 OK`, `404 Not Found` |
| `POST` | `/api/payments/<id>/refund` | Issue full simulated refund | `200 OK`, `404 Not Found`, `409 Conflict` |
| `GET` | `/api/dashboard` | Aggregated volumes, status counts, and KPIs | `200 OK` |
| `GET` | `/health` | Health and database connectivity status | `200 OK` |

### Sample cURL Request
```bash
curl -X POST http://127.0.0.1:5000/api/payments \
  -H "Content-Type: application/json" \
  -d '{
    "amount_paise": 25000,
    "currency": "INR",
    "description": "Order #1024 - Annual Subscription",
    "idempotency_key": "order-1024-token"
  }'
```

---

## 6. Project Structure

```
payflow/
├── app.py                 # Flask app, HTTP routes, JSON/HTML error handlers
├── db.py                  # SQLite connection helper, foreign key pragmas, schema init
├── services.py            # Business logic: idempotency, validations, ACID refunds, metrics
├── requirements.txt       # Dependencies (Flask)
├── README.md              # Project documentation and interview talking points
├── instance/              # Local SQLite database (payflow.db)
├── templates/
│   ├── base.html          # Base layout, navbar, simulation modal, toast container
│   ├── dashboard.html     # Metrics overview, quick presets, recent activity table
│   ├── transactions.html  # Full filterable transaction table with search & pagination
│   ├── payment_detail.html# Transaction breakdown, status history stepper, refund action
│   ├── api_docs.html      # REST documentation & interview cheat sheet
│   └── error.html         # User-friendly error display (400, 404, 409, 500)
├── static/
│   ├── css/
│   │   └── style.css      # Custom fintech dashboard styling (responsive, accessible)
│   └── js/
│       ├── app.js         # Modal control, toasts, live paise conversion, idempotency demo
│       └── dashboard.js   # Metric auto-refresh and preset runners
└── tests/
    └── test_payments.py   # 13 automated unit & integration tests
```

---

## 7. How to Explain This Project in an Interview

### 60-Second Elevator Pitch
> *"PayFlow is a simulated payment gateway and transaction ledger platform I built using Python Flask, SQLite, and vanilla JavaScript. Rather than a basic CRUD app, I focused on core financial engineering patterns.*
>
> *First, I implemented an idempotency key mechanism so that retrying the same request returns the original payment record without creating a duplicate charge. If someone alters the payload with the same key, it catches the conflict with an HTTP 409.*
>
> *Second, I stored all amounts as integer paise rather than floating-point rupees to eliminate IEEE 754 precision errors.*
>
> *Third, for refunds, I implemented a strict state machine: only succeeded payments can be refunded, exactly once. The refund record, status update, and audit log write are wrapped in an atomic database transaction with automatic rollback on failure.*
>
> *The project also includes an automated test suite verifying edge cases, state violations, and SQL injection defense."*

### Top Interview Questions & Answers

**Q: Why store money as an integer in paise?**  
*A: Computers use binary floating-point representation (IEEE 754), which cannot represent numbers like `0.1` or `0.2` exactly. In Python, `0.1 + 0.2 == 0.30000000000000004`. Over thousands of transactions, floating-point math causes rounding discrepancies. Representing currency in its smallest minor unit (paise) ensures exact arithmetic using integers.*

**Q: How does the idempotency key prevent double-charging?**  
*A: Before inserting a payment, we query the unique `idempotency_key`. If the key exists with identical parameters (amount, currency, description), we return the existing payment with `HTTP 200` without inserting a new row. If the key exists but the parameters were tampered with, we return `HTTP 409 Conflict`.*

**Q: Why use a database transaction for refunds?**  
*A: A refund requires three writes: inserting into `refunds`, updating `payments` status to `refunded`, and appending an audit record to `status_history`. If the second or third write fails, `with conn:` triggers a rollback so the database never ends up in a corrupted state.*
