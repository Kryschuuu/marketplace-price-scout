# 🛍️ Marketplace Price Scout

A powerful, production-ready price comparison scraper for German marketplaces (Kleinanzeigen, eBay, Hardwareschotte). Monitor product prices, identify deals, and track market trends in real-time.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue)
![Flask](https://img.shields.io/badge/flask-3.0+-green)

## 🎯 Features

✅ **Multi-Platform Scraping**
- Kleinanzeigen (classifieds)
- eBay Germany
- Hardwareschotte (hardware reference prices)

✅ **Smart Price Analysis**
- Trimmed mean calculation (removes outliers)
- Price difference percentage vs. market average
- Best deal highlighting

✅ **Production-Ready**
- Rate limiting (10 requests/minute)
- Input validation & sanitization
- Comprehensive error handling & logging
- CORS enabled for cross-origin requests
- Timeout protection (60 seconds)
- Parallel scraping for speed

✅ **User-Friendly Dashboard**
- Real-time search with live results
- Price filtering (min/max)
- Blacklist keywords (exclude search results)
- Responsive design (mobile & desktop)
- Dark theme UI

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
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
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
4. Click "Start Live Search"
5. Results appear in real-time with price comparisons

## 🔧 API Reference

### POST /api/scrape

Scrape all marketplaces for a product.

**Request:**
```json
{
  "query": "iPhone 15 Pro",
  "minPrice": 250,
  "maxPrice": 1200,
  "blacklist": ["hülle", "defekt", "ovp"]
}
```

**Response:**
```json
{
  "items": [
    {
      "platform": "Kleinanzeigen",
      "title": "iPhone 15 Pro 128GB Schwarz",
      "price": 899.50,
      "url": "https://www.kleinanzeigen.de/s-...",
      "diff": -5.2
    }
  ],
  "avgPrice": 950.00,
  "indexPrice": 899.99,
  "count": 42
}
```

### GET /health

Health check endpoint for monitoring.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

## ⚙️ Configuration

Edit `config.example.json` and save as `config.json` to customize:

```json
{
  "flask": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false
  },
  "scraper": {
    "timeout": 15,
    "rate_limit": 1,
    "max_retries": 2
  },
  "api": {
    "rate_limit_per_minute": 10,
    "max_results": 100
  }
}
```

## 🐛 Known Issues & Limitations

⚠️ **Website Changes**: Marketplace HTML structures change frequently. Scrapers may break temporarily.

⚠️ **Rate Limiting**: Some sites block scrapers. The tool uses cloudflare-bypass, but may still be blocked.

⚠️ **Cloudflare**: Hardwareschotte may require special handling. Falls back to standard requests if `cloudscraper` fails.

⚠️ **Legal**: Scraping may violate Terms of Service on some platforms. Use responsibly.

## 🔒 Security

- ✅ Input validation & sanitization
- ✅ Rate limiting to prevent abuse
- ✅ Timeout protection (60s max)
- ✅ CORS headers for safety
- ✅ No sensitive data stored
- ✅ No authentication bypass (just data scraping)

## 🛠️ Development

### Run with Debug Mode

```bash
FLASK_DEBUG=True python app.py
```

### View Logs

Logs are printed to console with timestamps:
```
2024-01-15 10:30:45,123 - INFO - Scraping query: 'iPhone 15 Pro'
2024-01-15 10:30:48,456 - INFO - Found 42 results
```

### Project Structure

```
marketplace-price-scout/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── config.example.json    # Configuration template
├── .env.example          # Environment variables template
├── .gitignore            # Git ignore rules
├── README.md             # This file
└── LICENSE               # MIT License
```

## 📊 Performance

- **Parallel Scraping**: Uses ThreadPoolExecutor for 3x faster results
- **Rate Limiting**: 1 second delay between platform requests
- **Timeout**: 60 seconds max per request
- **Max Results**: 100 items per platform

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the **MIT License** - see [LICENSE](LICENSE) file for details.

## ⚖️ Disclaimer

**Legal Notice**: This tool is for educational and personal use only. Scraping marketplaces may violate their Terms of Service. The author assumes no responsibility for misuse. Always:

- Check marketplace Terms of Service
- Respect rate limits and robots.txt
- Don't overwhelm servers with requests
- Use responsibly and ethically

## 🆘 Troubleshooting

### "No results found"
- Marketplace might be blocked or down
- Search term might be too specific
- Try different keywords

### "Request timeout"
- Network connection slow
- Website slow to respond
- Try again in a few moments

### "Cloudflare error"
- Website has strong bot protection
- cloudscraper may need updating: `pip install --upgrade cloudscraper`
- May need manual intervention

### Application won't start
- Port 5000 already in use: `FLASK_PORT=5001 python app.py`
- Dependencies not installed: `pip install -r requirements.txt`
- Python version too old: Requires Python 3.8+

## 📈 Future Roadmap

- [ ] Database storage for price history
- [ ] Price trend charts
- [ ] Email alerts for price drops
- [ ] More marketplaces (Vinted, Rebuy, etc.)
- [ ] Docker support
- [ ] REST API authentication
- [ ] Admin dashboard

## 💬 Questions?

Open an [Issue](https://github.com/Kryschuuu/marketplace-price-scout/issues) or [Discussion](https://github.com/Kryschuuu/marketplace-price-scout/discussions)!

---

**Made with ❤️ by [Kryschuuu](https://github.com/Kryschuuu)**
