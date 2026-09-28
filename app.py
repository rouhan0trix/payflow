"""
PayFlow: Payment & Transaction Management Platform (Flask App)
Provides both REST API endpoints and web UI views for simulated payments.
"""

import os
import sqlite3
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    abort,
    redirect,
    url_for,
)
from werkzeug.exceptions import HTTPException
from db import get_db, close_db, init_db, utc_now_iso
import services


def create_app(test_config=None):
    """Application factory for PayFlow."""
    app = Flask(__name__, instance_relative_config=True)

    # Default configuration
    app.config.from_mapping(
        SECRET_KEY="payflow-dev-secret-key-change-in-prod",
        DATABASE=os.path.join(app.instance_path, "payflow.db"),
    )

    if test_config:
        app.config.from_mapping(test_config)

    # Ensure instance directory exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Register database teardown
    app.teardown_appcontext(close_db)

    # Initialize tables on startup
    with app.app_context():
        init_db(app.config["DATABASE"])

    # -------------------------------------------------------------
    # Error Handlers
    # -------------------------------------------------------------
    @app.errorhandler(services.ValidationError)
    def handle_validation_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": str(e), "code": "VALIDATION_ERROR"}), 400
        return render_template("error.html", error_title="Invalid Request", error_message=str(e), status_code=400), 400

    @app.errorhandler(services.NotFoundError)
    def handle_not_found_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": str(e), "code": "NOT_FOUND"}), 404
        return render_template("error.html", error_title="Not Found", error_message=str(e), status_code=404), 404

    @app.errorhandler(services.ConflictError)
    def handle_conflict_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": str(e), "code": "CONFLICT"}), 409
        return render_template("error.html", error_title="Conflict / Invalid State", error_message=str(e), status_code=409), 409

    @app.errorhandler(404)
    def handle_http_404(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found.", "code": "NOT_FOUND"}), 404
        return render_template("error.html", error_title="Page Not Found", error_message="The requested page could not be located.", status_code=404), 404

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        if isinstance(e, HTTPException):
            return e
        if request.path.startswith("/api/"):
            return jsonify({"error": "An internal server error occurred.", "code": "SERVER_ERROR"}), 500
        return render_template("error.html", error_title="Server Error", error_message="An unexpected server error occurred.", status_code=500), 500

    # -------------------------------------------------------------
    # Web UI Routes
    # -------------------------------------------------------------
    @app.route("/")
    def index():
        """Dashboard overview: metrics, quick test simulator, recent payments."""
        metrics = services.get_dashboard_metrics()
        return render_template("dashboard.html", metrics=metrics)

    @app.route("/transactions")
    def transactions_page():
        """Transactions list page with search, filter tabs, and detail modal."""
        status_filter = request.args.get("status", "all")
        search_query = request.args.get("search", "")
        page = max(1, request.args.get("page", 1, type=int))
        limit = 20
        offset = (page - 1) * limit

        result = services.list_payments(
            status=status_filter,
            search=search_query,
            limit=limit,
            offset=offset,
        )

        total_pages = max(1, (result["total"] + limit - 1) // limit)

        return render_template(
            "transactions.html",
            payments=result["items"],
            total=result["total"],
            status_filter=status_filter,
            search_query=search_query,
            current_page=page,
            total_pages=total_pages,
        )

    @app.route("/transactions/<payment_id>")
    def transaction_detail_page(payment_id):
        """Dedicated page for a single transaction showing history and refund action."""
        try:
            payment = services.get_payment_details(payment_id)
            return render_template("payment_detail.html", payment=payment)
        except services.NotFoundError:
            abort(404)

    @app.route("/docs")
    def docs_page():
        """Interactive API documentation and technical interview study guide."""
        return render_template("api_docs.html")

    # -------------------------------------------------------------
    # REST API Endpoints
    # -------------------------------------------------------------
    @app.route("/health", methods=["GET"])
    def health_check():
        """Basic application and database connectivity check."""
        try:
            db = get_db()
            db.execute("SELECT 1").fetchone()
            db_status = "connected"
        except Exception:
            db_status = "error"

        return jsonify({
            "status": "ok",
            "service": "PayFlow API",
            "version": "1.0.0",
            "database": db_status,
            "timestamp": utc_now_iso(),
        }), 200

    @app.route("/api/payments", methods=["POST"])
    def api_create_payment():
        """
        Create a simulated payment with idempotency handling.
        Returns 201 for a newly created payment.
        Returns 200 for a valid idempotency key replay with identical payload.
        Returns 400 for validation errors.
        Returns 409 for idempotency key payload conflicts.
        """
        payload = request.get_json(silent=True)
        if payload is None:
            raise services.ValidationError("Request body must be valid JSON.")

        payment, is_replay = services.create_payment(payload)
        response_data = dict(payment)
        response_data["formatted_amount_inr"] = services.format_inr(response_data["amount_paise"])
        response_data["is_replay"] = is_replay

        status_code = 200 if is_replay else 201
        return jsonify(response_data), status_code

    @app.route("/api/payments", methods=["GET"])
    def api_list_payments():
        """
        List payments with optional status filtering and search.
        Query parameters:
          - status: all | succeeded | failed | refunded | pending
          - search: string (matches ID, description, or idempotency_key)
          - limit: integer (1..100, default 50)
          - offset: integer (default 0)
        """
        status_filter = request.args.get("status")
        search_query = request.args.get("search")
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)

        data = services.list_payments(
            status=status_filter,
            search=search_query,
            limit=limit,
            offset=offset,
        )
        return jsonify(data), 200

    @app.route("/api/payments/<payment_id>", methods=["GET"])
    def api_get_payment(payment_id):
        """Get payment details, refund information, and status change audit log."""
        payment = services.get_payment_details(payment_id)
        return jsonify(payment), 200

    @app.route("/api/payments/<payment_id>/refund", methods=["POST"])
    def api_refund_payment(payment_id):
        """
        Issue a full simulated refund for an eligible succeeded payment.
        Returns 200 on success.
        Returns 404 if payment does not exist.
        Returns 409 if payment is not succeeded or has already been refunded.
        """
        updated_payment = services.refund_payment(payment_id)
        return jsonify({
            "message": "Refund processed successfully.",
            "payment": updated_payment,
        }), 200

    @app.route("/api/dashboard", methods=["GET"])
    def api_dashboard_metrics():
        """Get summary metrics, status counts, and total settled volumes."""
        metrics = services.get_dashboard_metrics()
        return jsonify(metrics), 200

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Starting PayFlow on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
