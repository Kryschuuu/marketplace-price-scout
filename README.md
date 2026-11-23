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
- Rate limiting (configurable)
- Input validation & sanitization
- Comprehensive error handling & logging
- **Log Terminal Tab** (Live error/info tracking)
- CORS enabled for cross-origin requests
- Timeout protection (60 seconds)
- Parallel scraping for speed

✅ **User-Friendly Dashboard**
- Real-time search with live results
- Price filtering (min/max)
- Blacklist keywords (exclude search results)
- **Platform Selection** (Toggle marketplaces per search)
- Responsive design (mobile & desktop)
- Dark theme UI

## Version

Current release: **1.2.0** (see [CHANGELOG](CHANGELOG.md))

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

Edit `config.json` or use environment variables:

```json
{
  "flask": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false
  },
  "scraper": {
    "timeout": 15,
    "rate_limit": 0.5,
    "max_retries": 2,
    "user_agent": "Mozilla/5.0"
  },
  "platforms": {
    "kleinanzeigen_enabled": true,
    "ebay_enabled": true,
    "hardwareschotte_enabled": true,
    "vinted_enabled": true,
    "mydealz_enabled": true,
    "amazon_enabled": true
  },
  "pricing": {
    "trim_percent": 0.15,
    "min_price_threshold": 50
  },
  "api": {
    "rate_limit_per_minute": 10,
    "max_results": 100
  }
}
```

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
⚠️ **Legal**: Scraping may violate Terms of Service on some platforms. Use responsibly.

## 🔒 Security

- ✅ Input validation & sanitization
- ✅ Rate limiting to prevent abuse
- ✅ Timeout protection (60s max)
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
