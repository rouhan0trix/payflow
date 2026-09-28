"""
Business logic and transaction services for PayFlow.
Handles payment validation, idempotency verification, ACID refund transactions,
and dashboard metric aggregations.
"""

import re
import secrets
from datetime import datetime, timezone
from db import get_db, utc_now_iso


class ValidationError(Exception):
    """Raised when client input fails format, boundary, or type rules."""
    pass


class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""
    pass


class ConflictError(Exception):
    """Raised on idempotency payload mismatch or invalid state machine transitions."""
    pass


def validate_payment_payload(data):
    """
    Strict validation of payment creation payload.
    Ensures:
      - amount_paise is a positive integer (not float, string, or boolean)
      - currency is 'INR'
      - description is a bounded string (1..255 chars)
      - idempotency_key is a non-empty string (1..64 chars)
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")

    # 1. Validate amount_paise
    if "amount_paise" not in data:
        raise ValidationError("Field 'amount_paise' is required.")

    amount = data["amount_paise"]
    # In Python, isinstance(True, int) is True, so explicitly check type
    if type(amount) is not int:
        raise ValidationError("Field 'amount_paise' must be an integer representing minor currency units.")
    if amount <= 0:
        raise ValidationError("Field 'amount_paise' must be a strictly positive integer (> 0).")
    if amount > 100_000_000:  # Max 10 Lakh INR (1,000,000.00 INR = 100,000,000 paise)
        raise ValidationError("Field 'amount_paise' exceeds the maximum allowed simulation limit (100,000,000 paise).")

    # 2. Validate currency
    currency = data.get("currency", "INR")
    if not isinstance(currency, str) or currency.strip().upper() != "INR":
        raise ValidationError("Only 'INR' currency is supported in this educational version.")
    currency = currency.strip().upper()

    # 3. Validate description
    description = data.get("description")
    if description is None or not isinstance(description, str) or not description.strip():
        raise ValidationError("Field 'description' is required and must not be empty.")
    description = description.strip()
    if len(description) > 255:
        raise ValidationError("Field 'description' cannot exceed 255 characters.")

    # 4. Validate idempotency_key
    idempotency_key = data.get("idempotency_key")
    if idempotency_key is None or not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValidationError("Field 'idempotency_key' is required to ensure safe retries.")
    idempotency_key = idempotency_key.strip()
    if len(idempotency_key) > 64:
        raise ValidationError("Field 'idempotency_key' cannot exceed 64 characters.")

    # 5. Optional simulation status override ('succeeded', 'failed', 'pending')
    sim_status = data.get("simulate_status", "succeeded")
    if sim_status not in ("succeeded", "failed", "pending"):
        raise ValidationError("Invalid 'simulate_status'. Allowed values are: 'succeeded', 'failed', 'pending'.")

    return {
        "amount_paise": amount,
        "currency": currency,
        "description": description,
        "idempotency_key": idempotency_key,
        "simulate_status": sim_status,
    }


def format_inr(amount_paise):
    """Format paise integer into human-readable INR string (e.g., 25000 -> '250.00')."""
    rupees = amount_paise / 100.0
    return f"{rupees:,.2f}"


def create_payment(data, conn=None):
    """
    Creates a simulated payment with idempotency protection.
    Returns:
        tuple: (payment_dict, is_replay: bool)
    Raises:
        ValidationError: if payload is invalid
        ConflictError: if idempotency key reused with different payload
    """
    validated = validate_payment_payload(data)
    db = conn or get_db()

    # Step 1: Idempotency Check
    cursor = db.execute(
        "SELECT * FROM payments WHERE idempotency_key = ?",
        (validated["idempotency_key"],)
    )
    existing = cursor.fetchone()

    if existing:
        existing_dict = dict(existing)
        # Compare payload: amount_paise, currency, description
        payload_matches = (
            existing_dict["amount_paise"] == validated["amount_paise"]
            and existing_dict["currency"] == validated["currency"]
            and existing_dict["description"] == validated["description"]
        )

        if payload_matches:
            # Replay scenario: Return existing record cleanly (HTTP 200)
            return existing_dict, True
        else:
            # Conflict scenario: Same key reused with different data (HTTP 409)
            raise ConflictError(
                f"Idempotency key '{validated['idempotency_key']}' was already used with a different request payload."
            )

    # Step 2: New Payment Record Generation
    payment_id = f"pay_{secrets.token_hex(8)}"
    now = utc_now_iso()
    status = validated["simulate_status"]

    # Step 3: Atomic database transaction
    with db:
        db.execute(
            """
            INSERT INTO payments (
                id, amount_paise, currency, description, status,
                idempotency_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payment_id,
                validated["amount_paise"],
                validated["currency"],
                validated["description"],
                status,
                validated["idempotency_key"],
                now,
                now,
            )
        )

        # Initial status history record
        history_note = f"Simulated payment initialized with status: {status}"
        db.execute(
            """
            INSERT INTO status_history (
                payment_id, old_status, new_status, changed_at, note
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (payment_id, None, status, now, history_note)
        )

    # Return created payment record
    created = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    return dict(created), False


def refund_payment(payment_id, conn=None):
    """
    Performs a full simulated refund for an eligible payment.
    Enforces state machine rules:
      - Payment must exist (NotFoundError)
      - Payment must be in 'succeeded' status (ConflictError if pending, failed, or refunded)
      - No prior refund record may exist (ConflictError)
    Executes in a single atomic database transaction.
    """
    if not payment_id or not isinstance(payment_id, str):
        raise ValidationError("Valid payment ID is required.")

    db = conn or get_db()
    cursor = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id.strip(),))
    payment = cursor.fetchone()

    if not payment:
        raise NotFoundError(f"Payment with ID '{payment_id}' not found.")

    payment_dict = dict(payment)
    current_status = payment_dict["status"]

    # State validation
    if current_status == "refunded":
        raise ConflictError(f"Payment '{payment_id}' has already been refunded.")

    if current_status != "succeeded":
        raise ConflictError(
            f"Cannot refund payment with status '{current_status}'. Only 'succeeded' payments can be refunded."
        )

    # Check refunds table guard
    existing_refund = db.execute(
        "SELECT id FROM refunds WHERE payment_id = ?",
        (payment_id,)
    ).fetchone()

    if existing_refund:
        raise ConflictError(f"A refund record already exists for payment '{payment_id}'.")

    refund_id = f"rf_{secrets.token_hex(8)}"
    now = utc_now_iso()

    # Atomic write: Insert refund, update payment, record status history
    with db:
        db.execute(
            """
            INSERT INTO refunds (id, payment_id, amount_paise, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (refund_id, payment_id, payment_dict["amount_paise"], now)
        )

        db.execute(
            """
            UPDATE payments
            SET status = 'refunded', updated_at = ?
            WHERE id = ?
            """,
            (now, payment_id)
        )

        db.execute(
            """
            INSERT INTO status_history (
                payment_id, old_status, new_status, changed_at, note
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (payment_id, "succeeded", "refunded", now, "Full simulated refund issued")
        )

    # Return updated payment details
    return get_payment_details(payment_id, conn=db)


def get_payment_details(payment_id, conn=None):
    """
    Fetches a payment record along with refund details (if any) and full status history.
    """
    if not payment_id or not isinstance(payment_id, str):
        raise ValidationError("Valid payment ID is required.")

    db = conn or get_db()
    payment_row = db.execute(
        "SELECT * FROM payments WHERE id = ?",
        (payment_id.strip(),)
    ).fetchone()

    if not payment_row:
        raise NotFoundError(f"Payment with ID '{payment_id}' not found.")

    data = dict(payment_row)
    data["formatted_amount_inr"] = format_inr(data["amount_paise"])

    # Fetch refund record if any
    refund_row = db.execute(
        "SELECT * FROM refunds WHERE payment_id = ?",
        (payment_id.strip(),)
    ).fetchone()
    if refund_row:
        r_dict = dict(refund_row)
        r_dict["formatted_amount_inr"] = format_inr(r_dict["amount_paise"])
        data["refund"] = r_dict
    else:
        data["refund"] = None

    # Fetch status history ordered chronologically
    history_rows = db.execute(
        """
        SELECT id, old_status, new_status, changed_at, note
        FROM status_history
        WHERE payment_id = ?
        ORDER BY changed_at ASC, id ASC
        """,
        (payment_id.strip(),)
    ).fetchall()

    data["status_history"] = [dict(row) for row in history_rows]
    return data


def list_payments(status=None, search=None, limit=50, offset=0, conn=None):
    """
    Retrieves payments ordered newest first, with optional status filtering and search.
    Parameterized SQL protects against injection.
    """
    db = conn or get_db()

    query = "SELECT * FROM payments WHERE 1=1"
    count_query = "SELECT COUNT(*) as total FROM payments WHERE 1=1"
    params = []

    if status and status.strip() and status.strip().lower() != "all":
        status_clean = status.strip().lower()
        query += " AND status = ?"
        count_query += " AND status = ?"
        params.append(status_clean)

    if search and search.strip():
        search_pattern = f"%{search.strip()}%"
        query += " AND (id LIKE ? OR description LIKE ? OR idempotency_key LIKE ?)"
        count_query += " AND (id LIKE ? OR description LIKE ? OR idempotency_key LIKE ?)"
        params.extend([search_pattern, search_pattern, search_pattern])

    # Count total matching rows
    total_row = db.execute(count_query, params).fetchone()
    total_count = total_row["total"] if total_row else 0

    # Fetch paginated rows
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    paged_params = list(params)
    paged_params.extend([max(1, min(limit, 100)), max(0, offset)])

    rows = db.execute(query, paged_params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["formatted_amount_inr"] = format_inr(d["amount_paise"])
        results.append(d)

    return {
        "items": results,
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


def get_dashboard_metrics(conn=None):
    """
    Calculates summary totals and aggregated amounts directly from database records.
    """
    db = conn or get_db()

    # Aggregate status counts
    counts_rows = db.execute(
        """
        SELECT status, COUNT(*) as cnt, COALESCE(SUM(amount_paise), 0) as total_paise
        FROM payments
        GROUP BY status
        """
    ).fetchall()

    counts_by_status = {
        "succeeded": 0,
        "failed": 0,
        "refunded": 0,
        "pending": 0,
    }
    amount_by_status = {
        "succeeded": 0,
        "failed": 0,
        "refunded": 0,
        "pending": 0,
    }

    total_payments = 0

    for row in counts_rows:
        st = row["status"]
        c = row["cnt"]
        paise = row["total_paise"]
        if st in counts_by_status:
            counts_by_status[st] = c
            amount_by_status[st] = paise
        total_payments += c

    succeeded_paise = amount_by_status["succeeded"]
    refunded_paise = amount_by_status["refunded"]
    net_revenue_paise = succeeded_paise  # Net settled volume (refunded is excluded from current active settled)
    gross_volume_paise = succeeded_paise + refunded_paise

    success_rate = (
        round((counts_by_status["succeeded"] + counts_by_status["refunded"]) / total_payments * 100, 1)
        if total_payments > 0
        else 0.0
    )

    # Fetch recent 5 transactions
    recent_rows = db.execute(
        "SELECT * FROM payments ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    recent_transactions = []
    for r in recent_rows:
        d = dict(r)
        d["formatted_amount_inr"] = format_inr(d["amount_paise"])
        recent_transactions.append(d)

    return {
        "total_payments": total_payments,
        "counts": counts_by_status,
        "amounts_paise": {
            "succeeded": succeeded_paise,
            "refunded": refunded_paise,
            "gross_volume": gross_volume_paise,
        },
        "formatted": {
            "succeeded_inr": format_inr(succeeded_paise),
            "refunded_inr": format_inr(refunded_paise),
            "gross_volume_inr": format_inr(gross_volume_paise),
        },
        "success_rate_percent": success_rate,
        "recent_transactions": recent_transactions,
    }
