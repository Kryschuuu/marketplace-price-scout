"""Logging & error terminal in-memory buffer.

The dashboard polls ``GET /api/logs`` once per second. To keep that cheap and
to make polling resumable (client sends the last sequence number it saw), each
entry carries a monotonically increasing sequence number.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import List

# Global buffer for the "Log Terminal" tab
_LOCK = threading.Lock()
_LOG_BUFFER: deque[tuple[int, str]] = deque(maxlen=1000)
_SEQ = 0


class TerminalHandler(logging.Handler):
    """Appends formatted log records to the in-memory terminal buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        global _SEQ
        try:
            msg = self.format(record)
        except Exception:
            self.handleError(record)
            return
        try:
            with _LOCK:
                _SEQ += 1
                _LOG_BUFFER.append((_SEQ, msg))
        except Exception:
            self.handleError(record)


def get_terminal_logs(limit: int = 200, since: int | None = None) -> List[str]:
    """Return the latest log lines (newest first)."""
    return get_log_snapshot(limit=limit, since=since)["logs"]


def get_log_snapshot(limit: int = 200, since: int | None = None) -> dict:
    """Return log lines plus cursor information for incremental polling.

    ``since`` restricts the response to entries newer than that sequence
    number, which keeps polling cheap and lets clients recover after a
    rate-limited gap.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 200
    limit = max(1, min(limit, 2000))

    with _LOCK:
        entries = list(_LOG_BUFFER)
        latest = _SEQ

    if since is not None:
        try:
            since = int(since)
        except (TypeError, ValueError):
            since = None
    truncated = False
    if since is not None:
        if since > latest:
            since = latest
        first_available = entries[0][0] if entries else latest
        truncated = since < first_available - 1 and bool(entries)
        entries = [entry for entry in entries if entry[0] > since]

    selected = entries[-limit:]
    return {
        "logs": [msg for _, msg in reversed(selected)],
        "latestSeq": latest,
        "oldestSeq": selected[0][0] if selected else latest,
        "truncated": truncated,
        "total": len(_LOG_BUFFER),
    }


def clear_terminal() -> int:
    """Clear the log terminal buffer. Returns the number of removed lines."""
    with _LOCK:
        removed = len(_LOG_BUFFER)
        _LOG_BUFFER.clear()
    return removed


def configure_buffer_size(max_entries: int) -> None:
    """Resize the ring buffer before any handler is attached."""
    global _LOG_BUFFER
    with _LOCK:
        max_entries = max(10, int(max_entries))
        if _LOG_BUFFER.maxlen == max_entries:
            return
        entries = list(_LOG_BUFFER)
        _LOG_BUFFER = deque(entries, maxlen=max_entries)


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

    # Do not double-log through the root logger (Flask/Werkzeug access logs).
    logger.propagate = False
    return logger
