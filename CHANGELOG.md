# Changelog

## 1.3.0 — 2026-11-23

Bug-fix release for the issues visible in `Running on http12700150.txt`.

### Fixed
- **Platform selection was ignored.** `POST /api/scrape` validated `platforms`
  but `scrape_all_platforms()` iterated `config.platforms` only, so a search with
  every platform except Kleinanzeigen disabled still hit Vinted (406) and
  Amazon (503) — and logged those errors under a "No results found" line.
  The request selection and the configuration are now intersected and disabled
  platforms are reported as `skipped` without any outbound request.
- **`POST /api/scrape` returned `200` for failed searches.** HTTP 406/503 were
  logged at INFO level and turned into empty lists, indistinguishable from
  "no offers". Scrapers now raise typed errors (`PlatformBlocked`,
  `PlatformTimeout`, `ScraperError`); the endpoint answers `503` when every
  selected marketplace was blocked/timed out and `502` for other total failures.
  Partial failures stay `200` but are listed in `warnings`.
- **`GET /api/logs` was rate limited to death.** It was subject to the global
  `10 per minute` limiter while the dashboard polls every second (429 from
  21:03:14 onward). Log polling now has its own budget (default 120/min),
  returns JSON with `Retry-After` on 429, and supports incremental polling via
  `?since=<seq>`; the UI backs off instead of hammering the endpoint.
- **Malformed input produced `500`s.** `minPrice: "abc"`, `platforms: []`,
  `blacklist: [{}]` etc. raised `TypeError`/`AttributeError` inside the handler.
  Validation is now strictly typed and maps to HTTP 400.
- **No retries/timeouts worth the name.** `max_retries` was configured but never
  used and `timeout` was passed as a kwarg to sessions that ignore it.
  Requests now have explicit timeouts, exponential backoff with jitter,
  `Retry-After` support and a bounded total scrape deadline.
- **Weak User-Agent.** `config.example.json` shipped `"Mozilla/5.0"`, a classic
  bot signature; short/blank agents are now replaced by a full Chrome UA and
  browser-like `Accept`/`Accept-Language`/`Sec-Fetch-*` headers are sent.
- **`.env` was ignored.** `python-dotenv` was a dependency but `load_dotenv()`
  was never called.
- **Sessions were recreated per platform per request.** One cached session per
  platform (with an optional homepage warm-up) keeps cookies alive.
- **Log buffer was not thread-safe** and grew a new deque on resize; it is now
  guarded by a lock and reports sequence numbers (`latestSeq`/`oldestSeq`).
- `config.example.json` keys `rate_limit`, `user_agent`, `deadline` and
  `api.log_rate_limit_per_minute` were parsed incorrectly or not at all;
  unknown platform keys are now reported instead of ignored.
- Log clearing no longer immediately re-logs into the buffer it just cleared.

### Changed
- `scrape_all_platforms()` returns a `ScrapeReport` (items + per-platform
  outcomes) instead of a bare list; all calls updated.
- `/health` reports the version and platform switches.
- `GET /api/scrape` responses gained `platforms`, `warnings`, `durationMs`,
  `query`; CORS is configurable via `CORS_ORIGINS`.
- Added `tests/` coverage for all of the above (43 tests, no network access).

## 1.2.0 — 2026-11-23
- **Refactor**: Restructured repository into `marketplace_price_scout/` package.
- **Feature**: Added **Log Terminal Tab** in the UI to track live scraping logs and error messages.
- **Feature**: Added **Platform Selection** checkboxes to choose which marketplaces to search.
- **Bugfix**: Fixed Amazon/Vinted/eBay scrapers returning HTTP 503/406 by implementing robust fallback logic and `curl_cffi`/`cloudscraper` selection.
- **Bugfix**: Improved error handling and logging for "No results found" scenarios.
- **Update**: Added `config.py` for centralized configuration management.
- **Update**: Added unit tests for validation and adapters.
- **Update**: Bumped version to 1.2.0.

## 1.1.0 — 2026-11-23
- Added Vinted Germany, mydealz and Amazon Germany search adapters.
- Hardened input validation, outbound URLs, concurrency and browser rendering.
