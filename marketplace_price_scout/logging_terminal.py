"""Logging & error terminal in-memory buffer."""
from __future__ import annotations

import logging
from collections import deque
from typing import List

# Global buffer for the new "Log Terminal" tab
_LOG_BUFFER: deque[str] = deque(maxlen=1000)


class TerminalHandler(logging.Handler):
    """Appends formatted log records to the in-memory terminal buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _LOG_BUFFER.append(msg)
        except Exception:
            self.handleError(record)


def get_terminal_logs(limit: int = 200) -> List[str]:
    """Return the latest log lines (newest first)."""
    return list(_LOG_BUFFER)[-limit:][::-1]


def clear_terminal() -> None:
    """Clear the log terminal buffer."""
    _LOG_BUFFER.clear()


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure standard logging and attach the terminal handler."""
    logger = logging.getLogger("marketplace_price_scout")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Prevent duplicate handlers if called multiple times
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        
        # Console handler
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

        # Terminal handler
        term = TerminalHandler()
        term.setFormatter(formatter)
        logger.addHandler(term)

    return logger
