"""Main entry point to run the app from root."""
from __future__ import annotations

import sys

from marketplace_price_scout.app import app

if __name__ == "__main__":
    # Forward arguments to app.run if needed
    app.run()
