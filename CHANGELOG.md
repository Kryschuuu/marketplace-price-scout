# Changelog

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
