import json
import time
import traceback
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from bs4 import BeautifulSoup
import cloudscraper
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for cross-origin requests
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)

# Configuration
config = {
    "timeout": 15,
    "rate_limit": 1,
    "max_retries": 2,
    "min_price_threshold": 50,
    "trim_percent": 0.15,
    "max_results": 100
}

# ==========================================
# BACKEND: ROBUST SCRAPER LOGIC
# ==========================================

def get_scraper():
    """Returns a scraper instance with proper error handling."""
    try:
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        scraper.timeout = config['timeout']
        return scraper
    except Exception as e:
        logger.warning(f"Cloudscraper initialization failed: {e}. Using requests fallback.")
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        session.timeout = config['timeout']
        return session

def validate_input(query, min_price, max_price, blacklist):
    """Validate and sanitize user input."""
    if not query or len(query.strip()) == 0:
        raise ValueError("Search query cannot be empty")
    if len(query) > 200:
        raise ValueError("Search query too long (max 200 characters)")
    if min_price < 0 or max_price < 0:
        raise ValueError("Prices cannot be negative")
    if min_price > max_price:
        raise ValueError("Min price cannot exceed max price")
    if len(blacklist) > 50:
        raise ValueError("Too many blacklist items (max 50)")
    
    return (
        query.strip()[:200],
        float(min_price),
        float(max_price),
        [item.strip()[:50] for item in blacklist if item.strip()][:50]
    )

def clean_price(price_str):
    """Extract numeric price from string with error handling."""
    if not price_str:
        return 0.0
    try:
        cleaned = price_str.replace("€", "").replace("VB", "").replace("Preis auf Anfrage", "0")
        cleaned = cleaned.replace(".", "").replace(",", ".").strip()
        filtered = "".join([c for c in cleaned if c.isdigit() or c == '.'])
        return float(filtered) if filtered else 0.0
    except Exception as e:
        logger.debug(f"Price parsing error for '{price_str}': {e}")
        return 0.0

def is_valid_item(title, price, min_price, max_price, blacklist):
    """Check if an item meets all criteria."""
    if not title or price is None:
        return False
    
    title_lower = title.lower()
    for word in blacklist:
        word = word.strip().lower()
        if word and word in title_lower:
            return False
    
    if price < min_price or price > max_price:
        return False
    
    return True

def get_hardwareschotte_index(query, scraper):
    """Fetch reference price from Hardwareschotte."""
    try:
        formatted_query = query.replace(" ", "+")
        url = f"https://www.hardwareschotte.de/suche/?searchstring={formatted_query}"
        response = scraper.get(url, timeout=config['timeout'])
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            prices = [clean_price(p.get_text()) for p in soup.select('.articlePrice, .price')]
            prices = [p for p in prices if p > config['min_price_threshold']]
            if prices:
                return min(prices)
    except requests.Timeout:
        logger.warning(f"Hardwareschotte timeout for query: {query}")
    except Exception as e:
        logger.error(f"Hardwareschotte error: {e}")
    
    return None

def scrape_kleinanzeigen(query, min_price, max_price, blacklist, scraper):
    """Scrape Kleinanzeigen marketplace."""
    items = []
    try:
        formatted_query = query.replace(" ", "-")
        url = f"https://www.kleinanzeigen.de/s-{formatted_query}/k0"
        response = scraper.get(url, timeout=config['timeout'])
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            ads = soup.select('article.aditem')[:config['max_results']]
            
            for ad in ads:
                try:
                    title_elem = ad.select_one('a.ellipsis') or ad.select_one('h2 a')
                    price_elem = ad.select_one('p.aditem-main--middle--price-shipping--price')
                    
                    if title_elem and price_elem:
                        title = title_elem.get_text(strip=True)
                        price = clean_price(price_elem.get_text())
                        
                        if is_valid_item(title, price, min_price, max_price, blacklist):
                            link = "https://www.kleinanzeigen.de" + title_elem.get('href', '')
                            items.append({
                                "platform": "Kleinanzeigen",
                                "title": title[:100],
                                "price": price,
                                "url": link
                            })
                except Exception as e:
                    logger.debug(f"Error parsing Kleinanzeigen item: {e}")
                    continue
    except requests.Timeout:
        logger.warning(f"Kleinanzeigen timeout for query: {query}")
    except Exception as e:
        logger.error(f"Kleinanzeigen scraping error: {e}")
    
    return items

def scrape_ebay(query, min_price, max_price, blacklist, scraper):
    """Scrape eBay marketplace."""
    items = []
    try:
        formatted_query = query.replace(" ", "+")
        url = f"https://www.ebay.de/sch/i.html?_nkw={formatted_query}&_sacat=0&LH_ItemCondition=3000|1000"
        response = scraper.get(url, timeout=config['timeout'])
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            ebay_items = soup.select('div.s-item__info')[:config['max_results']]
            
            for item in ebay_items:
                try:
                    title_elem = item.select_one('.s-item__title')
                    price_elem = item.select_one('.s-item__price')
                    link_elem = item.select_one('a.s-item__link')
                    
                    if title_elem and price_elem and link_elem:
                        title = title_elem.get_text(strip=True).replace("Neues Angebot", "")
                        price = clean_price(price_elem.get_text())
                        
                        if "Shop-Artikel" not in title and is_valid_item(title, price, min_price, max_price, blacklist):
                            url = link_elem.get('href', '#').split("?")[0]
                            items.append({
                                "platform": "eBay",
                                "title": title[:100],
                                "price": price,
                                "url": url
                            })
                except Exception as e:
                    logger.debug(f"Error parsing eBay item: {e}")
                    continue
    except requests.Timeout:
        logger.warning(f"eBay timeout for query: {query}")
    except Exception as e:
        logger.error(f"eBay scraping error: {e}")
    
    return items

def calculate_trimmed_mean(items, trim_percent=None):
    """Calculate trimmed mean price (removes outliers)."""
    if trim_percent is None:
        trim_percent = config['trim_percent']
    
    if not items:
        return 0.0
    
    prices = sorted([i['price'] for i in items])
    
    if len(prices) < 4:
        return sum(prices) / len(prices)
    
    trim_count = int(len(prices) * trim_percent)
    trimmed = prices[trim_count:-trim_count] if trim_count > 0 else prices
    
    return sum(trimmed) / len(trimmed) if trimmed else 0.0

def scrape_all_platforms(query, min_price, max_price, blacklist):
    """Scrape all platforms in parallel for better performance."""
    scraper = get_scraper()
    items = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(scrape_kleinanzeigen, query, min_price, max_price, blacklist, scraper): "Kleinanzeigen",
            executor.submit(scrape_ebay, query, min_price, max_price, blacklist, scraper): "eBay",
        }
        
        for future in as_completed(futures):
            try:
                platform_items = future.result(timeout=config['timeout'])
                items.extend(platform_items)
                time.sleep(config['rate_limit'])  # Rate limiting
            except Exception as e:
                logger.error(f"Error in {futures[future]}: {e}")
    
    return items

# ==========================================
# FRONTEND: HTML & JS
# ==========================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de" class="h-full bg-slate-950">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Marketplace Price Scout - Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="text-slate-300 h-full flex flex-col font-sans antialiased overflow-hidden">

    <nav class="bg-slate-900 border-b border-slate-800 shrink-0 p-4 flex justify-between items-center">
        <div class="flex items-center gap-3">
            <div class="bg-emerald-500/20 text-emerald-400 p-2 rounded-lg border border-emerald-500/30"><i class="fa-solid fa-magnifying-glass-dollar fa-lg"></i></div>
            <span class="text-xl font-bold text-white tracking-tight">Marketplace <span class="text-emerald-500">Price Scout</span></span>
        </div>
        <span class="text-xs text-slate-500">v1.0.0</span>
    </nav>

    <div class="flex flex-1 overflow-hidden flex-col md:flex-row">
        <!-- Sidebar -->
        <aside class="w-full md:w-80 bg-slate-900 border-r border-slate-800 overflow-y-auto shrink-0 p-5 space-y-6">
            <div>
                <h3 class="text-xs font-bold uppercase text-slate-500 mb-3">🔍 Search Configuration</h3>
                <div class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium mb-1 text-slate-300">Search Term</label>
                        <input type="text" id="queryInput" value="iPhone 15 Pro" placeholder="e.g. iPhone 15 Pro" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none">
                        <p class="text-xs text-slate-500 mt-1">Max 200 characters</p>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-sm font-medium mb-1 text-slate-300">Min €</label>
                            <input type="number" id="minPriceInput" value="250" min="0" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none">
                        </div>
                        <div>
                            <label class="block text-sm font-medium mb-1 text-slate-300">Max €</label>
                            <input type="number" id="maxPriceInput" value="1200" min="0" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none">
                        </div>
                    </div>
                    <div>
                        <label class="block text-sm font-medium mb-1 text-slate-300">Blacklist (comma-separated)</label>
                        <input type="text" id="blacklistInput" value="hülle, defekt, ovp, tausche, bastler" placeholder="e.g. hülle, defekt" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-emerald-500 focus:outline-none">
                        <p class="text-xs text-slate-500 mt-1">Exclude listings with these words</p>
                    </div>
                </div>
            </div>
            <hr class="border-slate-800">
            <div>
                <button id="searchBtn" onclick="runAnalysis()" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-3 rounded-lg text-sm shadow transition flex items-center justify-center gap-2">
                    <i class="fa-solid fa-magnifying-glass"></i> Start Live Search
                </button>
            </div>
        </aside>

        <!-- Main Workspace -->
        <main class="flex-1 overflow-y-auto bg-slate-950 p-4 relative">
            <div id="loadingOverlay" class="absolute inset-0 bg-slate-950/90 backdrop-blur-sm z-10 hidden flex-col items-center justify-center">
                <i class="fa-solid fa-circle-notch fa-spin text-4xl text-emerald-500 mb-4"></i>
                <h2 class="text-xl font-bold text-white mb-2">Scraping Live Data...</h2>
                <p class="text-slate-400 text-sm text-center px-4">Please wait. Searching across platforms may take a few seconds.</p>
            </div>
            
            <!-- Error Banner -->
            <div id="errorBanner" class="hidden mb-4 p-4 bg-rose-500/20 border border-rose-500/50 rounded-lg text-rose-300 text-sm">
                <div class="flex items-center font-bold mb-1"><i class="fa-solid fa-triangle-exclamation mr-2"></i> Error Occurred</div>
                <p id="errorText" class="break-words"></p>
            </div>

            <div class="max-w-6xl mx-auto space-y-6">
                <!-- KPIs -->
                <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
                    <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
                        <p class="text-xs text-slate-400 font-semibold uppercase">Market Average</p>
                        <h3 class="text-xl md:text-2xl font-bold text-white mt-1" id="kpi-avg">-- €</h3>
                    </div>
                    <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
                        <p class="text-xs text-slate-400 font-semibold uppercase">Reference Price</p>
                        <h3 class="text-xl md:text-2xl font-bold text-indigo-400 mt-1" id="kpi-new">-- €</h3>
                    </div>
                    <div class="col-span-2 md:col-span-1 bg-slate-900 border border-emerald-500/30 rounded-xl p-4 bg-emerald-900/10">
                        <p class="text-xs text-emerald-400/80 font-semibold uppercase">Best Deal</p>
                        <h3 class="text-xl md:text-2xl font-bold text-emerald-400 mt-1" id="kpi-min">-- €</h3>
                    </div>
                </div>

                <!-- Results -->
                <div class="bg-slate-900 border border-slate-800 rounded-xl shadow-lg overflow-hidden">
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm whitespace-nowrap">
                            <thead class="bg-slate-900 text-slate-400 text-xs uppercase border-b border-slate-800">
                                <tr>
                                    <th class="px-4 py-3">Platform</th>
                                    <th class="px-4 py-3">Item</th>
                                    <th class="px-4 py-3 text-right">Price</th>
                                    <th class="px-4 py-3 text-right">Difference</th>
                                    <th class="px-4 py-3 text-center">Link</th>
                                </tr>
                            </thead>
                            <tbody id="resultsTableBody" class="divide-y divide-slate-800/50">
                                <tr><td colspan="5" class="px-4 py-12 text-center text-slate-500">Ready for first search.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        async function runAnalysis() {
            const overlay = document.getElementById('loadingOverlay');
            const errorBanner = document.getElementById('errorBanner');
            const searchBtn = document.getElementById('searchBtn');
            
            overlay.classList.remove('hidden');
            overlay.classList.add('flex');
            errorBanner.classList.add('hidden');
            searchBtn.disabled = true;
            
            const query = document.getElementById('queryInput').value.trim();
            const minPrice = parseFloat(document.getElementById('minPriceInput').value);
            const maxPrice = parseFloat(document.getElementById('maxPriceInput').value);
            const blacklist = document.getElementById('blacklistInput').value
                .split(',').map(x => x.trim()).filter(x => x);
            
            // Client-side validation
            if (!query) {
                showError('Search term cannot be empty.');
                overlay.classList.add('hidden');
                overlay.classList.remove('flex');
                searchBtn.disabled = false;
                return;
            }
            if (query.length > 200) {
                showError('Search term too long (max 200 characters).');
                overlay.classList.add('hidden');
                overlay.classList.remove('flex');
                searchBtn.disabled = false;
                return;
            }
            if (minPrice > maxPrice) {
                showError('Min price cannot exceed max price.');
                overlay.classList.add('hidden');
                overlay.classList.remove('flex');
                searchBtn.disabled = false;
                return;
            }
            
            const payload = {
                query: query,
                minPrice: minPrice,
                maxPrice: maxPrice,
                blacklist: blacklist
            };

            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout
                
                const response = await fetch('/api/scrape', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                    signal: controller.signal
                });
                
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.error || `HTTP Status ${response.status}`);
                }
                
                const data = await response.json();
                updateDashboard(data);
                
            } catch (error) {
                let reason = error.message;
                if (error.name === 'AbortError') {
                    reason = 'Request timeout. The scraper took too long. Try again or use simpler search terms.';
                } else if (reason === "Failed to fetch") {
                    reason = 'Network error. Check your connection or if an ad blocker is blocking requests.';
                }
                showError(reason);
            } finally {
                overlay.classList.add('hidden');
                overlay.classList.remove('flex');
                searchBtn.disabled = false;
            }
        }
        
        function showError(message) {
            const errorBanner = document.getElementById('errorBanner');
            const errorText = document.getElementById('errorText');
            errorBanner.classList.remove('hidden');
            errorText.innerText = message;
        }

        function updateDashboard(data) {
            document.getElementById('kpi-avg').innerText = data.avgPrice > 0 ? `${data.avgPrice.toFixed(2)} €` : '-- €';
            document.getElementById('kpi-new').innerText = data.indexPrice ? `${data.indexPrice.toFixed(2)} €` : '-- €';
            if(data.items.length > 0) document.getElementById('kpi-min').innerText = `${data.items[0].price.toFixed(2)} €`;

            const tbody = document.getElementById('resultsTableBody');
            if(data.items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" class="px-4 py-8 text-center text-rose-400">No results found.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.items.map(item => {
                let diffColor = item.diff <= 0 ? 'text-emerald-400' : 'text-rose-400';
                return `
                    <tr class="hover:bg-slate-800/80 transition">
                        <td class="px-4 py-3"><span class="px-2 py-1 rounded text-xs bg-slate-800 text-slate-300">${item.platform}</span></td>
                        <td class="px-4 py-3 font-medium text-white max-w-[150px] md:max-w-md truncate" title="${item.title}">${item.title}</td>
                        <td class="px-4 py-3 font-bold text-white text-right">${item.price.toFixed(2)} €</td>
                        <td class="px-4 py-3 ${diffColor} text-right font-semibold">${item.diff > 0 ? '+' : ''}${item.diff.toFixed(1)}%</td>
                        <td class="px-4 py-3 text-center">
                            <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="p-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 inline-block"><i class="fa-solid fa-arrow-up-right-from-square"></i></a>
                        </td>
                    </tr>
                `;
            }).join('');
        }
    </script>
</body>
</html>
"""

# ==========================================
# FLASK ROUTES
# ==========================================

@app.route('/')
def index():
    """Serve the main dashboard."""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/scrape', methods=['POST'])
@limiter.limit("10 per minute")
def api_scrape():
    """API endpoint for scraping marketplaces."""
    try:
        req_data = request.json or {}
        
        # Extract and validate input
        query = req_data.get('query', '')
        min_price = float(req_data.get('minPrice', 0))
        max_price = float(req_data.get('maxPrice', 10000))
        blacklist = req_data.get('blacklist', [])
        
        if isinstance(blacklist, str):
            blacklist = [x.strip() for x in blacklist.split(',')]
        
        # Validate input
        query, min_price, max_price, blacklist = validate_input(
            query, min_price, max_price, blacklist
        )
        
        logger.info(f"Scraping query: '{query}' (€{min_price}-€{max_price})")
        
        # Scrape all platforms in parallel
        items = scrape_all_platforms(query, min_price, max_price, blacklist)
        
        if not items:
            logger.info(f"No results found for query: '{query}'")
            return jsonify({
                "items": [],
                "avgPrice": 0,
                "indexPrice": None,
                "count": 0
            })
        
        # Get reference price
        index_price = get_hardwareschotte_index(query, get_scraper())
        avg_price = calculate_trimmed_mean(items)
        ref_price = avg_price
        
        if index_price and index_price < avg_price:
            ref_price = index_price
        
        # Calculate price differences
        for item in items:
            item['diff'] = ((item['price'] - ref_price) / ref_price * 100) if ref_price > 0 else 0
        
        # Sort by price
        items = sorted(items, key=lambda x: x['price'])
        
        logger.info(f"Found {len(items)} results for query: '{query}'")
        
        return jsonify({
            "items": items[:config['max_results']],
            "avgPrice": round(ref_price, 2),
            "indexPrice": round(index_price, 2) if index_price else None,
            "count": len(items)
        })

    except ValueError as e:
        logger.warning(f"Input validation error: {e}")
        return jsonify({"error": f"Invalid input: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Backend error: {e}", exc_info=True)
        return jsonify({"error": f"Backend error: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Marketplace Price Scout on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)
