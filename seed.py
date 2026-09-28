"""
Database seeding script for PayFlow.
Populates initial sample transactions so the dashboard has rich demonstration data.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app import create_app
import services

def seed():
    app = create_app()
    with app.app_context():
        # Check if already seeded
        metrics = services.get_dashboard_metrics()
        if metrics["total_payments"] > 0:
            print(f"[*] Database already contains {metrics['total_payments']} payments. Skipping seed.")
            return

        print("[*] Seeding sample transactions...")

        sample_payments = [
            {
                "amount_paise": 250000,
                "currency": "INR",
                "description": "Order #1001 - Enterprise Annual License",
                "idempotency_key": "seed-ent-1001",
                "simulate_status": "succeeded"
            },
            {
                "amount_paise": 49900,
                "currency": "INR",
                "description": "Order #1002 - Monthly Cloud Hosting Tier",
                "idempotency_key": "seed-cld-1002",
                "simulate_status": "succeeded"
            },
            {
                "amount_paise": 15000,
                "currency": "INR",
                "description": "Order #1003 - Domain Registration (.in)",
                "idempotency_key": "seed-dom-1003",
                "simulate_status": "succeeded"
            },
            {
                "amount_paise": 75000,
                "currency": "INR",
                "description": "Order #1004 - Developer Hardware Token",
                "idempotency_key": "seed-tok-1004",
                "simulate_status": "failed"
            },
            {
                "amount_paise": 120000,
                "currency": "INR",
                "description": "Order #1005 - Security Audit Service",
                "idempotency_key": "seed-aud-1005",
                "simulate_status": "pending"
            }
        ]

        created_payments = []
        for p in sample_payments:
            pay, _ = services.create_payment(p)
            created_payments.append(pay)
            print(f" [+] Created payment {pay['id']} ({pay['status']}) - INR {services.format_inr(pay['amount_paise'])}")

        # Refund one of the succeeded payments (Order #1003)
        to_refund = created_payments[2]  # Domain registration
        refunded = services.refund_payment(to_refund["id"])
        print(f" [✓] Refunded payment {to_refund['id']} - Refund ID: {refunded['refund']['id']}")

        print("[*] Seeding complete! Database is ready.")

if __name__ == "__main__":
    seed()
