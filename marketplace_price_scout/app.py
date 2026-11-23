"""Flask application entry point."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

from marketplace_price_scout import __version__
from marketplace_price_scout.config import RESULT_PLATFORMS, ScoutConfig
from marketplace_price_scout.logging_terminal import (
    configure_buffer_size,
    clear_terminal,
    get_log_snapshot,
    setup_logging,
)
from marketplace_price_scout.scrapers.adapters import (
    calculate_trimmed_mean,
    get_hardwareschotte_index,
    resolve_platforms,
    scrape_all_platforms,
)
from marketplace_price_scout.scrapers.validation import validate_input, validate_platforms
from marketplace_price_scout.templates.index import HTML_TEMPLATE

# Load configuration (module level so `from ...app import config` keeps working)
config = ScoutConfig.from_env()
logger = setup_logging(config.log_level)
configure_buffer_size(config.log_max_entries)


def _int_arg(name: str, default: int | None) -> int | None:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer") from None


def create_app(cfg: ScoutConfig | None = None) -> Flask:
    """Build the Flask app for the given configuration."""
    cfg = cfg or config
    app_logger = logging.getLogger("marketplace_price_scout")

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024  # a scrape payload is tiny
    app.config["SCOUT_CONFIG"] = cfg
    app.json.sort_keys = False

    if cfg.cors_origins:
        CORS(app, origins=list(cfg.cors_origins))
    else:
        CORS(app)

    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[],  # every endpoint opts in explicitly below
        storage_uri=cfg.ratelimit_storage_uri,
        headers_enabled=True,
    )
    app.extensions["scout_limiter"] = limiter

    scrape_limit = f"{cfg.api_rate_limit_per_minute} per minute"
    log_limit = f"{cfg.log_rate_limit_per_minute} per minute"
    log_clear_limit = f"{cfg.log_clear_rate_limit_per_minute} per minute"

    # ---------------------------- error handling ---------------------------
    @app.errorhandler(429)
    def handle_rate_limit(exc):  # noqa: ANN001
        """Return a JSON 429 with Retry-After instead of an HTML page."""
        retry_after = 1
        limit_item = getattr(exc, "limit", None)
        if limit_item is not None:
            try:
                retry_after = max(1, int(limit_item.get_expiry()))
            except Exception:
                retry_after = 1
        response = jsonify(
            {
                "error": "Rate limit exceeded. Please retry later.",
                "retryAfter": retry_after,
            }
        )
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response

    @app.errorhandler(ValueError)
    def handle_value_error(exc):  # noqa: ANN001
        app_logger.warning("Input validation error: %s", exc)
        return jsonify({"error": f"Invalid input: {exc}"}), 400

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):  # noqa: ANN001
        if isinstance(exc, HTTPException):
            return exc
        app_logger.exception("Backend error")
        return jsonify({"error": "Internal server error. Please try again later."}), 500

    # ------------------------------- routes --------------------------------
    @app.route("/")
    def index():
        """Serve the main dashboard."""
        return render_template_string(HTML_TEMPLATE, version=__version__)

    @app.route("/api/scrape", methods=["POST"])
    @limiter.limit(scrape_limit)
    def api_scrape():
        """API endpoint for scraping marketplaces."""
        started = datetime.now(timezone.utc)

        req_data = request.get_json(silent=True)
        if req_data is None:
            raise ValueError("Request body must be valid JSON")
        if not isinstance(req_data, dict):
            raise ValueError("Request body must be a JSON object")

        query, min_price, max_price, blacklist = validate_input(
            req_data.get("query", ""),
            req_data.get("minPrice", 0),
            req_data.get("maxPrice", 10000),
            req_data.get("blacklist", []),
        )
        selection = validate_platforms(req_data.get("platforms"))
        enabled = resolve_platforms(cfg, selection)

        app_logger.info(
            "Scraping query: '%s' (€%s-%s) | Platforms: %s",
            query,
            min_price,
            max_price,
            {name: value for name, value in enabled.items()},
        )

        result_platforms = [
            name for name in RESULT_PLATFORMS if enabled.get(name)
        ]
        report = scrape_all_platforms(
            query, min_price, max_price, blacklist, cfg, app_logger, selection=selection
        )

        index_price = None
        if result_platforms and enabled.get("hardwareschotte") and report.items:
            index_price = get_hardwareschotte_index(query, None, cfg, app_logger)

        items = report.items
        avg_price = calculate_trimmed_mean(items, config=cfg)
        ref_price = avg_price
        if index_price and 0 < index_price < avg_price:
            ref_price = index_price

        for item in items:
            item["diff"] = (
                round((item["price"] - ref_price) / ref_price * 100, 2)
                if ref_price > 0
                else 0.0
            )
        items = sorted(items, key=lambda entry: entry["price"])

        duration = (datetime.now(timezone.utc) - started).total_seconds()
        payload = {
            "query": query,
            "items": items[: cfg.max_results],
            "avgPrice": round(avg_price, 2),
            "indexPrice": round(index_price, 2) if index_price else None,
            "count": len(items),
            "platforms": [outcome.as_dict() for outcome in report.outcomes],
            "warnings": report.warnings,
            "durationMs": int(duration * 1000),
        }

        # No searchable platform selected: this is a client error, not a
        # successful empty search.
        if not result_platforms:
            return (
                jsonify(
                    {
                        **payload,
                        "message": "No result platform was selected.",
                    }
                ),
                400,
            )

        # Every selected platform failed: report an error instead of pretending
        # the marketplace had no offers (the old 200 + "No results found" bug).
        if report.all_failed:
            app_logger.error("All platforms failed for query '%s': %s", query, report.warnings)
            statuses = {outcome.status_code for outcome in report.failed}
            blocked = bool(statuses & {401, 403, 406, 429})
            timed_out = any(outcome.timed_out for outcome in report.failed)
            if blocked or 503 in statuses or timed_out or report.deadline_exceeded:
                return (
                    jsonify(
                        {
                            **payload,
                            "error": "All selected marketplaces failed "
                            "(blocked or timed out). Please retry later.",
                        }
                    ),
                    503,
                )
            return (
                jsonify(
                    {
                        **payload,
                        "error": "Scraping failed on all selected marketplaces.",
                    }
                ),
                502,
            )

        if not items:
            app_logger.info(
                "No results found for query: '%s' (successful platforms: %s)",
                query,
                ", ".join(outcome.platform for outcome in report.succeeded) or "none",
            )
            payload["message"] = "No matching offers found."
            return jsonify(payload)

        app_logger.info("Found %s results for query: '%s'", len(items), query)
        return jsonify(payload)

    @app.route("/api/logs", methods=["GET"])
    @limiter.limit(log_limit)
    def api_logs():
        """Return terminal logs (incremental polling via ?since=<seq>)."""
        limit = _int_arg("limit", 200)
        since = _int_arg("since", None)
        snapshot = get_log_snapshot(limit=limit or 200, since=since)
        response = jsonify(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/api/logs/clear", methods=["POST"])
    @limiter.limit(log_clear_limit)
    def api_logs_clear():
        """Clear terminal logs."""
        removed = clear_terminal()
        # Log at DEBUG so the confirmation does not immediately repopulate the
        # buffer the user just cleared.
        app_logger.debug("Log terminal cleared (%s entries)", removed)
        return jsonify({"status": "cleared", "removed": removed})

    @app.route("/health", methods=["GET"])
    @limiter.limit(log_limit)
    def health():
        """Health check endpoint for monitoring."""
        return jsonify(
            {
                "status": "healthy",
                "version": __version__,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platforms": cfg.platforms,
            }
        )

    @app.after_request
    def add_security_headers(response):  # noqa: ANN001
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    return app


app = create_app(config)


if __name__ == "__main__":
    logger.log(
        logging.INFO,
        "Starting Marketplace Price Scout v%s on http://%s:%s",
        __version__,
        config.host,
        config.port,
    )
    app.run(host=config.host, port=config.port, debug=config.debug, threaded=True)
