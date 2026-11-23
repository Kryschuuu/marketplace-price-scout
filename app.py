"""Main entry point to run the app from root."""
from __future__ import annotations

from marketplace_price_scout.app import app, config

if __name__ == "__main__":
    app.run(host=config.host, port=config.port, debug=config.debug, threaded=True)
