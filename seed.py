"""
Database seeding script for PayFlow.
Populates initial sample transactions so the dashboard has rich demonstration data.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import services

def seed_data(app=None):
    if app is None:
        from app import create_app
        app = create_app()

    with app.app_context():
        metrics = services.get_dashboard_metrics()
        if metrics["total_payments"] > 0:
            return

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

        if len(created_payments) >= 3:
            services.refund_payment(created_payments[2]["id"])

def seed():
    seed_data()
    print("[*] Database seeded successfully.")

if __name__ == "__main__":
    seed()
