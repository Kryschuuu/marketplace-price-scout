"""Flask application entry point."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from marketplace_price_scout.config import ScoutConfig, as_dict
from marketplace_price_scout.logging_terminal import setup_logging, get_terminal_logs, clear_terminal
from marketplace_price_scout.scrapers.adapters import (
    scrape_all_platforms,
    calculate_trimmed_mean,
    get_hardwareschotte_index,
)
from marketplace_price_scout.scrapers.validation import validate_input
from marketplace_price_scout.templates.index import HTML_TEMPLATE

# Load configuration
config = ScoutConfig.from_env()
logger = setup_logging(config.log_level)

app = Flask(__name__)
CORS(app)  # Enable CORS for cross-origin requests

# Rate limiting (use storage URI from config)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[f"{config.api_rate_limit_per_minute} per minute"],
    storage_uri=config.ratelimit_storage_uri,
)

# ==========================================#
# FLASK ROUTES
# ==========================================#

@app.route("/")
def index():
    """Serve the main dashboard."""
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/scrape", methods=["POST"])
@limiter.limit(f"{config.api_rate_limit_per_minute} per minute")
def api_scrape():
    """API endpoint for scraping marketplaces."""
    try:
        req_data = request.get_json(silent=True) or {}
        if not isinstance(req_data, dict):
            raise ValueError("Request body must be a JSON object")

        # Extract and validate input
        query = req_data.get("query", "")
        min_price = float(req_data.get("minPrice", 0))
        max_price = float(req_data.get("maxPrice", 10000))
        blacklist = req_data.get("blacklist", [])
        platforms_selection = req_data.get("platforms", {})

        # Validate input
        query, min_price, max_price, blacklist = validate_input(
            query, min_price, max_price, blacklist
        )

        logger.info(f"Scraping query: '{query}' (€{min_price}-{max_price}) | Platforms: {platforms_selection}")

        # Scrape enabled platforms in parallel (or sequentially respecting rate limits)
        items = scrape_all_platforms(query, min_price, max_price, blacklist, config, logger)

        # Filter items based on platform selection (adapters already filter, but double check)
        if platforms_selection:
            allowed = {k for k, v in platforms_selection.items() if v}
            items = [i for i in items if i["platform"].lower() in allowed]

        if not items:
            logger.info(f"No results found for query: '{query}'")
            return jsonify(
                {
                    "items": [],
                    "avgPrice": 0,
                    "indexPrice": None,
                    "count": 0,
                }
            )

        # Get reference price (only if hardwareschotte is enabled or requested)
        index_price = None
        if platforms_selection.get("hardwareschotte", config.platforms.get("hardwareschotte", True)):
            scraper = None  # get_hardwareschotte_index creates its own or uses shared
            index_price = get_hardwareschotte_index(query, scraper, config, logger)

        avg_price = calculate_trimmed_mean(items, config=config)
        ref_price = avg_price

        if index_price and index_price < avg_price:
            ref_price = index_price

        # Calculate price differences
        for item in items:
            item["diff"] = ((item["price"] - ref_price) / ref_price * 100) if ref_price > 0 else 0

        # Sort by price
        items = sorted(items, key=lambda x: x["price"])

        logger.info(f"Found {len(items)} results for query: '{query}'")

        return jsonify(
            {
                "items": items[: config.max_results],
                "avgPrice": round(ref_price, 2),
                "indexPrice": round(index_price, 2) if index_price else None,
                "count": len(items),
            }
        )

    except ValueError as e:
        logger.warning(f"Input validation error: {e}")
        return jsonify({"error": f"Invalid input: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Backend error: {e}", exc_info=True)
        return jsonify({"error": "Scraping failed. Please try again later."}), 500


@app.route("/api/logs", methods=["GET"])
def api_logs():
    """Return terminal logs."""
    return jsonify({"logs": get_terminal_logs()})


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    """Clear terminal logs."""
    clear_terminal()
    return jsonify({"status": "cleared"})


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for monitoring."""
    return jsonify(
        {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
    )


if __name__ == "__main__":
    host = config.host
    port = config.port
    debug = config.debug

    logger.info(f"Starting Marketplace Price Scout v1.2.0 on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)
