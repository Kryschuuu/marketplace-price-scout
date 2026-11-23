# 🛍️ Marketplace Price Scout

A powerful, production-ready price comparison scraper for German marketplaces (Kleinanzeigen, eBay, Vinted, mydealz, Amazon and Hardwareschotte). Monitor product prices, identify deals, and track market trends in real-time.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue)
![Flask](https://img.shields.io/badge/flask-3.0+-green)

## 🎯 Features

✅ **Multi-Platform Scraping** (Selectable per search)
- Kleinanzeigen (classifieds)
- eBay Germany
- Vinted Germany
- mydealz Germany
- Amazon Germany
- Hardwareschotte (hardware reference prices)

✅ **Smart Price Analysis**
- Trimmed mean calculation (removes outliers)
- Price difference percentage vs. market average
- Best deal highlighting

✅ **Production-Ready**
- Rate limiting (separate budgets for scraping vs. log polling)
- Input validation & sanitization (strict types → HTTP 400, never 500)
- Correct HTTP semantics: `200` only when at least one marketplace answered,
  `503`/`502` when every selected marketplace was blocked/failed
- Retries with exponential backoff + `Retry-After` support, per-request timeouts
  and an overall scrape deadline
- **Log Terminal Tab** (live, incremental polling — no more 429 storms)
- CORS configurable (`CORS_ORIGINS`)
- Parallel scraping with bounded worker pool

✅ **User-Friendly Dashboard**
- Real-time search with live results
- Price filtering (min/max)
- Blacklist keywords (exclude search results)
- **Platform Selection** (Toggle marketplaces per search)
- Responsive design (mobile & desktop)
- Dark theme UI

## Version

Current release: **1.3.0** (see [CHANGELOG](CHANGELOG.md))

## 📋 Requirements

- Python 3.8+
- pip (Python package manager)

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Kryschuuu/marketplace-price-scout.git
cd marketplace-price-scout
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) Create .env File

```bash
cp .env.example .env
```

Edit `.env` to customize:
```
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=False
SCRAPER_TIMEOUT=15
SCRAPER_MAX_RETRIES=2
API_RATE_LIMIT_PER_MINUTE=10
API_MAX_RESULTS=100
```

## 💻 Usage

### Start the Application

```bash
python app.py
# or, for production:
gunicorn -w 2 -b 0.0.0.0:5000 "marketplace_price_scout.app:app"
```

The web dashboard will be available at: **http://localhost:5000**

### Using the Dashboard

1. Enter a product name (e.g., "iPhone 15 Pro")
2. Set min/max price range (optional)
3. Add blacklist keywords to exclude listings (e.g., "hülle, defekt")
4. **Select Platforms** (Kleinanzeigen, eBay, Vinted, mydealz, Amazon, Hardwareschotte)
5. Click "Start Live Search"
6. Results appear in real-time with price comparisons
7. **Log Terminal Tab**: View live scraping logs and error messages

## ⚙️ Configuration

Edit `config.json` (copy `config.example.json`) or use environment variables
(see `.env.example`). Environment variables win over `config.json`.

| Key (JSON / env) | Default | Meaning |
|---|---|---|
| `scraper.timeout` / `SCRAPER_TIMEOUT` | `15` | per-request timeout (s) |
| `scraper.deadline` / `SCRAPER_DEADLINE` | `25` | total budget for one search (s) |
| `scraper.max_retries` / `SCRAPER_MAX_RETRIES` | `2` | retries per platform |
| `scraper.retry_backoff` / `SCRAPER_RETRY_BACKOFF` | `1.5` | exponential backoff base |
| `scraper.rate_limit` / `SCRAPER_RATE_LIMIT` | `0.0` | extra delay between platforms |
| `scraper.user_agent` / `SCRAPER_USER_AGENT` | Chrome UA | outbound User-Agent |
| `scraper.warmup` / `SCRAPER_WARMUP` | `true` | visit homepage first so cookies exist |
| `api.rate_limit_per_minute` / `API_RATE_LIMIT_PER_MINUTE` | `10` | limit for `POST /api/scrape` |
| `api.log_rate_limit_per_minute` / `API_LOG_RATE_LIMIT_PER_MINUTE` | `120` | limit for `GET /api/logs` |
| `api.cors_origins` / `CORS_ORIGINS` | `[]` (any) | allowed browser origins |
| `platforms.*_enabled` | `true` | globally enable/disable a platform |

All numeric values are clamped to a safe range, and a short/bogus User-Agent
(e.g. `Mozilla/5.0`) is replaced — that alone is a common cause of 406/503.

## 🔌 API

### `POST /api/scrape`

```json
{
  "query": "iPhone 15 Pro",
  "minPrice": 250,
  "maxPrice": 1200,
  "blacklist": ["hülle", "defekt"],
  "platforms": {"kleinanzeigen": true, "ebay": false, "vinted": false,
                "mydealz": false, "amazon": false, "hardwareschotte": false}
}
```

| Status | Meaning |
|---|---|
| `200` | at least one selected marketplace answered (result list may be empty) |
| `400` | invalid JSON/input, or no searchable platform selected |
| `429` | scrape rate limit hit (`Retry-After` header) |
| `502` | every selected marketplace failed (non-blocking error) |
| `503` | every selected marketplace blocked us (`401/403/406/429/503`) or timed out |

The body always contains `items`, `avgPrice`, `indexPrice`, `count`,
`platforms` (per-platform status) and `warnings` (per-platform failure reason).
A platform that is disabled in the request or in the config is reported as
`"skipped": true` and is **never** contacted.

### `GET /api/logs`

Incremental polling: pass `since=<latestSeq>` from the previous response to get
only new lines. Returns `logs` (newest first), `latestSeq`, `oldestSeq`,
`truncated` and `total`. Responses carry `Cache-Control: no-store`; the
dashboard polls once per second and backs off on `429` using `Retry-After`.

### `GET /health`, `POST /api/logs/clear`

Health probe (version + platform switches) and log buffer reset.

## 🧪 Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite never touches the network (HTTP clients are stubbed) and covers the
log-derived regressions: ignored platform selection, 406/503 handling, status
codes, retry/backoff, scrape deadline and 429 behaviour of the log endpoint.

## 🛠️ Project Structure

```
marketplace-price-scout/
├── marketplace_price_scout/          # Package root
│   ├── __init__.py                  # Version & package info
│   ├── app.py                       # Flask application & routes
│   ├── config.py                    # Configuration loader
│   ├── logging_terminal.py          # Log terminal buffer & handler
│   ├── scrapers/                    # Scraper logic
│   │   ├── adapters.py              # Platform adapters
│   │   └── validation.py            # Input validation
│   ├── templates/                   # HTML templates
│   │   └── index.html               # Dashboard with Log Terminal & Platform selection
│   └── static/                      # Static assets (optional)
├── app.py                           # Root entry point
├── requirements.txt                 # Python dependencies
├── config.example.json              # Configuration template
├── requirements-dev.txt             # Test/lint dependencies
├── .env.example                     # Environment variables template
├── .gitignore                       # Git ignore rules
├── README.md                        # This file
├── CHANGELOG.md                     # Release history
├── LICENSE                          # MIT License
└── tests/                           # Unit tests
    └── test_app.py                  # Test suite
```

## 🐛 Known Issues & Limitations

⚠️ **Website Changes**: Marketplace HTML structures change frequently. Scrapers may break temporarily.
⚠️ **Rate Limiting**: Some sites block scrapers. The tool uses cloudscraper/curl_cffi, but may still be blocked.
⚠️ **Cloudflare**: Hardwareschotte may require special handling. Falls back to standard requests if `cloudscraper` fails.
⚠️ **Bot walls**: Vinted (`406`) and Amazon (`503`) routinely block datacenter IPs. The code retries with backoff, warms up cookies and (if `curl_cffi` is installed) impersonates a Chrome TLS fingerprint, but cannot guarantee success. When *all* platforms are blocked the API now answers `503` instead of pretending there were no offers.
⚠️ **Legal**: Scraping may violate Terms of Service on some platforms. Use responsibly.

## 🔒 Security

- ✅ Input validation & sanitization
- ✅ Rate limiting to prevent abuse
- ✅ Per-request timeout + overall scrape deadline
- ✅ Strict input typing (no 500s from malformed JSON)
- ✅ Off-site result links rejected (no redirect/SSRF-style URLs)
- ✅ CORS headers for safety
- ✅ No sensitive data stored
- ✅ No authentication bypass (just data scraping)

## 📈 Future Roadmap

- [ ] Database storage for price history
- [ ] Price trend charts
- [ ] Email alerts for price drops
- [ ] Docker support
- [ ] REST API authentication
- [ ] Admin dashboard

## 💬 Questions?

Open an [Issue](https://github.com/Kryschuuu/marketplace-price-scout/issues) or [Discussion](https://github.com/Kryschuuu/marketplace-price-scout/discussions)!

---

**Made with ❤️ by [Kryschuuu](https://github.com/Kryschuuu)**
---
