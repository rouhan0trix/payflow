"""
Unit and integration tests for PayFlow Payment & Transaction Management Platform.
Tests all functional requirements, state machine transitions, idempotency behavior,
error codes, and database transaction safety.
"""

import json
import os
import tempfile
import unittest
import sqlite3

from app import create_app
import services


class PayFlowTestCase(unittest.TestCase):
    def setUp(self):
        """Set up an isolated test database and test client for each test."""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.app = create_app({
            "TESTING": True,
            "DATABASE": self.db_path,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up temporary database file."""
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # -------------------------------------------------------------
    # 1. Payment Creation Tests
    # -------------------------------------------------------------
    def test_create_valid_payment(self):
        """Valid payment creation returns 201 and creates exactly one database record."""
        payload = {
            "amount_paise": 25000,
            "currency": "INR",
            "description": "Order #1001 - Annual Subscription",
            "idempotency_key": "key-order-1001",
        }
        res = self.client.post("/api/payments", json=payload)
        self.assertEqual(res.status_code, 201)

        data = res.get_json()
        self.assertTrue(data["id"].startswith("pay_"))
        self.assertEqual(data["amount_paise"], 25000)
        self.assertEqual(data["currency"], "INR")
        self.assertEqual(data["status"], "succeeded")
        self.assertEqual(data["formatted_amount_inr"], "250.00")
        self.assertFalse(data["is_replay"])

        # Verify database record
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        payments = conn.execute("SELECT * FROM payments WHERE id = ?", (data["id"],)).fetchall()
        self.assertEqual(len(payments), 1)

        # Verify initial status history was created
        history = conn.execute("SELECT * FROM status_history WHERE payment_id = ?", (data["id"],)).fetchall()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["new_status"], "succeeded")
        conn.close()

    def test_invalid_amounts_rejected(self):
        """Zero, negative, float, string, or boolean amounts must be rejected with 400."""
        invalid_amounts = [0, -1500, 49.99, "2500", True, False, None]
        for amt in invalid_amounts:
            payload = {
                "amount_paise": amt,
                "currency": "INR",
                "description": "Test invalid amount",
                "idempotency_key": f"key-inv-{amt}",
            }
            res = self.client.post("/api/payments", json=payload)
            self.assertEqual(res.status_code, 400, f"Amount '{amt}' should be rejected with 400")
            err = res.get_json()
            self.assertEqual(err.get("code"), "VALIDATION_ERROR")

    def test_missing_or_invalid_fields(self):
        """Missing description or invalid currency must return 400."""
        # Missing description
        res = self.client.post("/api/payments", json={
            "amount_paise": 1000,
            "currency": "INR",
            "idempotency_key": "key-nodesc",
        })
        self.assertEqual(res.status_code, 400)

        # Empty description
        res = self.client.post("/api/payments", json={
            "amount_paise": 1000,
            "description": "   ",
            "idempotency_key": "key-emptydesc",
        })
        self.assertEqual(res.status_code, 400)

        # Unsupported currency
        res = self.client.post("/api/payments", json={
            "amount_paise": 1000,
            "currency": "USD",
            "description": "Demo USD",
            "idempotency_key": "key-usd",
        })
        self.assertEqual(res.status_code, 400)

    # -------------------------------------------------------------
    # 2. Idempotency Key Tests
    # -------------------------------------------------------------
    def test_idempotency_replay_identical_payload(self):
        """Replaying identical request returns 200, is_replay=True, and does not insert duplicate."""
        payload = {
            "amount_paise": 50000,
            "currency": "INR",
            "description": "Demo Laptop Purchase",
            "idempotency_key": "order-laptop-55",
        }

        # First request -> 201 Created
        res1 = self.client.post("/api/payments", json=payload)
        self.assertEqual(res1.status_code, 201)
        data1 = res1.get_json()

        # Second identical request -> 200 OK (replay)
        res2 = self.client.post("/api/payments", json=payload)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()

        self.assertEqual(data1["id"], data2["id"])
        self.assertTrue(data2["is_replay"])

        # Check total payments count in database remains exactly 1
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_idempotency_conflict_different_payload(self):
        """Reusing the same key with different amount or description returns 409 Conflict."""
        payload1 = {
            "amount_paise": 50000,
            "currency": "INR",
            "description": "Original Order",
            "idempotency_key": "key-same-123",
        }
        res1 = self.client.post("/api/payments", json=payload1)
        self.assertEqual(res1.status_code, 201)

        # Same key, different amount -> 409 Conflict
        payload2 = {
            "amount_paise": 99900,
            "currency": "INR",
            "description": "Original Order",
            "idempotency_key": "key-same-123",
        }
        res2 = self.client.post("/api/payments", json=payload2)
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(res2.get_json().get("code"), "CONFLICT")

        # Same key, different description -> 409 Conflict
        payload3 = {
            "amount_paise": 50000,
            "currency": "INR",
            "description": "Tampered description",
            "idempotency_key": "key-same-123",
        }
        res3 = self.client.post("/api/payments", json=payload3)
        self.assertEqual(res3.status_code, 409)

    # -------------------------------------------------------------
    # 3. Payment Retrieval & Status History Tests
    # -------------------------------------------------------------
    def test_get_payment_details_and_not_found(self):
        """Retrieve payment details and verify 404 for unknown IDs."""
        res_404 = self.client.get("/api/payments/pay_nonexistent")
        self.assertEqual(res_404.status_code, 404)

        # Create one
        create_res = self.client.post("/api/payments", json={
            "amount_paise": 12000,
            "currency": "INR",
            "description": "Test lookup",
            "idempotency_key": "key-lookup-1",
        })
        pay_id = create_res.get_json()["id"]

        get_res = self.client.get(f"/api/payments/{pay_id}")
        self.assertEqual(get_res.status_code, 200)
        data = get_res.get_json()
        self.assertEqual(data["id"], pay_id)
        self.assertEqual(data["amount_paise"], 12000)
        self.assertEqual(len(data["status_history"]), 1)
        self.assertIsNone(data["refund"])

    # -------------------------------------------------------------
    # 4. Refund & State Machine Tests
    # -------------------------------------------------------------
    def test_refund_successful_payment(self):
        """A succeeded payment can be refunded; updates status, logs refund & history."""
        create_res = self.client.post("/api/payments", json={
            "amount_paise": 30000,
            "currency": "INR",
            "description": "Refundable item",
            "idempotency_key": "key-ref-1",
        })
        pay_id = create_res.get_json()["id"]

        # Request refund
        refund_res = self.client.post(f"/api/payments/{pay_id}/refund")
        self.assertEqual(refund_res.status_code, 200)

        updated = refund_res.get_json()["payment"]
        self.assertEqual(updated["status"], "refunded")
        self.assertIsNotNone(updated["refund"])
        self.assertEqual(updated["refund"]["amount_paise"], 30000)
        self.assertTrue(updated["refund"]["id"].startswith("rf_"))

        # Verify status history timeline
        self.assertEqual(len(updated["status_history"]), 2)
        self.assertEqual(updated["status_history"][0]["new_status"], "succeeded")
        self.assertEqual(updated["status_history"][1]["new_status"], "refunded")

    def test_cannot_refund_twice(self):
        """Refunding an already refunded payment returns 409 Conflict."""
        create_res = self.client.post("/api/payments", json={
            "amount_paise": 30000,
            "currency": "INR",
            "description": "Double refund attempt",
            "idempotency_key": "key-ref-2",
        })
        pay_id = create_res.get_json()["id"]

        # First refund succeeds
        res1 = self.client.post(f"/api/payments/{pay_id}/refund")
        self.assertEqual(res1.status_code, 200)

        # Second refund fails with 409
        res2 = self.client.post(f"/api/payments/{pay_id}/refund")
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(res2.get_json().get("code"), "CONFLICT")

    def test_cannot_refund_failed_or_pending_payment(self):
        """Failed or pending payments cannot be refunded (returns 409)."""
        # Create failed payment
        res_fail = self.client.post("/api/payments", json={
            "amount_paise": 15000,
            "currency": "INR",
            "description": "Simulated failed payment",
            "idempotency_key": "key-fail-1",
            "simulate_status": "failed",
        })
        fail_id = res_fail.get_json()["id"]

        # Try refunding failed payment -> 409
        refund_fail_res = self.client.post(f"/api/payments/{fail_id}/refund")
        self.assertEqual(refund_fail_res.status_code, 409)

        # Create pending payment
        res_pend = self.client.post("/api/payments", json={
            "amount_paise": 15000,
            "currency": "INR",
            "description": "Simulated pending payment",
            "idempotency_key": "key-pend-1",
            "simulate_status": "pending",
        })
        pend_id = res_pend.get_json()["id"]

        # Try refunding pending payment -> 409
        refund_pend_res = self.client.post(f"/api/payments/{pend_id}/refund")
        self.assertEqual(refund_pend_res.status_code, 409)

    # -------------------------------------------------------------
    # 5. Dashboard Metrics & SQL Injection Tests
    # -------------------------------------------------------------
    def test_dashboard_metrics_aggregation(self):
        """Dashboard totals correctly aggregate stored records."""
        # 1 succeeded (100.00 INR = 10000 paise)
        self.client.post("/api/payments", json={
            "amount_paise": 10000,
            "description": "Item 1",
            "idempotency_key": "stat-1",
            "simulate_status": "succeeded",
        })
        # 1 failed (50.00 INR = 5000 paise)
        self.client.post("/api/payments", json={
            "amount_paise": 5000,
            "description": "Item 2",
            "idempotency_key": "stat-2",
            "simulate_status": "failed",
        })
        # 1 refunded (200.00 INR = 20000 paise)
        r = self.client.post("/api/payments", json={
            "amount_paise": 20000,
            "description": "Item 3",
            "idempotency_key": "stat-3",
            "simulate_status": "succeeded",
        })
        pid = r.get_json()["id"]
        self.client.post(f"/api/payments/{pid}/refund")

        dash_res = self.client.get("/api/dashboard")
        self.assertEqual(dash_res.status_code, 200)
        data = dash_res.get_json()

        self.assertEqual(data["total_payments"], 3)
        self.assertEqual(data["counts"]["succeeded"], 1)
        self.assertEqual(data["counts"]["failed"], 1)
        self.assertEqual(data["counts"]["refunded"], 1)
        self.assertEqual(data["amounts_paise"]["succeeded"], 10000)
        self.assertEqual(data["amounts_paise"]["refunded"], 20000)

    def test_sql_injection_defense(self):
        """Malicious SQL inputs are safely handled as literal strings by parameterized queries."""
        sql_payload = "'; DROP TABLE payments; --"
        res = self.client.post("/api/payments", json={
            "amount_paise": 7500,
            "currency": "INR",
            "description": sql_payload,
            "idempotency_key": "sql-test-key",
        })
        self.assertEqual(res.status_code, 201)

        # Ensure table still exists and data was stored verbatim
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT description FROM payments WHERE idempotency_key = 'sql-test-key'").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], sql_payload)

    def test_database_rollback_on_error(self):
        """Simulate a failure during refund transaction to verify ACID rollback behavior."""
        create_res = self.client.post("/api/payments", json={
            "amount_paise": 45000,
            "currency": "INR",
            "description": "Rollback test",
            "idempotency_key": "rollback-key-1",
        })
        pay_id = create_res.get_json()["id"]

        # Intentionally force a database error on inserting into status_history using a trigger
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TRIGGER force_refund_rollback
            BEFORE INSERT ON status_history
            WHEN NEW.new_status = 'refunded'
            BEGIN
                SELECT RAISE(ABORT, 'Simulated failure to verify ACID transaction rollback');
            END;
        """)
        conn.commit()

        # Calling services.refund_payment directly will hit the trigger inside 'with conn:'
        with self.assertRaises(sqlite3.IntegrityError):
            services.refund_payment(pay_id, conn=conn)

        # Verify that because 'with conn:' caught the error, rollback occurred:
        # 1. Payment status remains 'succeeded' (not 'refunded')
        # 2. No row was created in refunds table
        payment = conn.execute("SELECT * FROM payments WHERE id = ?", (pay_id,)).fetchone()
        refunds = conn.execute("SELECT * FROM refunds WHERE payment_id = ?", (pay_id,)).fetchall()
        conn.close()

        self.assertEqual(payment["status"], "succeeded")
        self.assertEqual(len(refunds), 0)

    def test_health_check(self):
        """Health endpoint returns status ok and database connected."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "connected")


if __name__ == "__main__":
    unittest.main()
