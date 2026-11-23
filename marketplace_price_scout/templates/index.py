"""Frontend HTML template with Log Terminal tab and Platform selection."""
from __future__ import annotations

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
        <span class="text-xs text-slate-500" id="versionBadge">v1.2.0</span>
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
                    
                    <!-- Platform Selection -->
                    <div>
                        <label class="block text-sm font-medium mb-1 text-slate-300">Platforms</label>
                        <div class="grid grid-cols-2 gap-2">
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="platform-kleinanzeigen" checked class="w-4 h-4 text-emerald-500 bg-slate-950 border-slate-700 rounded focus:ring-emerald-500">
                                <span class="text-sm text-slate-300">Kleinanzeigen</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="platform-ebay" checked class="w-4 h-4 text-emerald-500 bg-slate-950 border-slate-700 rounded focus:ring-emerald-500">
                                <span class="text-sm text-slate-300">eBay</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="platform-vinted" checked class="w-4 h-4 text-emerald-500 bg-slate-950 border-slate-700 rounded focus:ring-emerald-500">
                                <span class="text-sm text-slate-300">Vinted</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="platform-mydealz" checked class="w-4 h-4 text-emerald-500 bg-slate-950 border-slate-700 rounded focus:ring-emerald-500">
                                <span class="text-sm text-slate-300">mydealz</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="platform-amazon" checked class="w-4 h-4 text-emerald-500 bg-slate-950 border-slate-700 rounded focus:ring-emerald-500">
                                <span class="text-sm text-slate-300">Amazon</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="platform-hardwareschotte" checked class="w-4 h-4 text-emerald-500 bg-slate-950 border-slate-700 rounded focus:ring-emerald-500">
                                <span class="text-sm text-slate-300">Hardwareschotte</span>
                            </label>
                        </div>
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

            <!-- Tabs -->
            <div class="max-w-6xl mx-auto mb-4">
                <div class="flex border-b border-slate-800">
                    <button id="tabResults" onclick="switchTab('results')" class="px-6 py-2 border-b-2 border-emerald-500 text-emerald-500 font-medium text-sm">Results</button>
                    <button id="tabLogs" onclick="switchTab('logs')" class="px-6 py-2 border-b-2 border-transparent text-slate-500 hover:text-slate-300 font-medium text-sm">Log Terminal</button>
                </div>
            </div>

            <!-- Results Tab -->
            <div id="contentResults" class="max-w-6xl mx-auto space-y-6">
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

            <!-- Log Terminal Tab -->
            <div id="contentLogs" class="max-w-6xl mx-auto space-y-4 hidden">
                <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 h-[500px] overflow-y-auto font-mono text-xs text-emerald-400/90">
                    <div id="logTerminalBody" class="space-y-1">
                        <div>[SYSTEM] Log terminal initialized...</div>
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="clearLogs()" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-sm transition">Clear Terminal</button>
                </div>
            </div>
        </main>
    </div>

    <script>
        let currentTab = 'results';
        let logInterval = null;

        function switchTab(tab) {
            currentTab = tab;
            document.getElementById('contentResults').classList.toggle('hidden', tab !== 'results');
            document.getElementById('contentLogs').classList.toggle('hidden', tab !== 'logs');
            document.getElementById('tabResults').classList.toggle('border-emerald-500', tab === 'results');
            document.getElementById('tabResults').classList.toggle('text-emerald-500', tab === 'results');
            document.getElementById('tabResults').classList.toggle('border-transparent', tab !== 'results');
            document.getElementById('tabResults').classList.toggle('text-slate-500', tab !== 'results');
            document.getElementById('tabLogs').classList.toggle('border-emerald-500', tab === 'logs');
            document.getElementById('tabLogs').classList.toggle('text-emerald-500', tab === 'logs');
            document.getElementById('tabLogs').classList.toggle('border-transparent', tab !== 'logs');
            document.getElementById('tabLogs').classList.toggle('text-slate-500', tab !== 'logs');
            
            if (tab === 'logs') {
                fetchLogs();
                logInterval = setInterval(fetchLogs, 1000);
            } else {
                clearInterval(logInterval);
            }
        }

        function fetchLogs() {
            fetch('/api/logs')
                .then(res => res.json())
                .then(data => {
                    const body = document.getElementById('logTerminalBody');
                    body.innerHTML = data.logs.map(l => `<div>${escapeHtml(l)}</div>`).join('');
                    body.scrollTop = body.scrollHeight;
                })
                .catch(err => console.error('Failed to fetch logs', err));
        }

        function clearLogs() {
            fetch('/api/logs/clear', { method: 'POST' })
                .then(() => fetchLogs())
                .catch(err => console.error('Failed to clear logs', err));
        }

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
            
            // Platform selection
            const platforms = {
                kleinanzeigen: document.getElementById('platform-kleinanzeigen').checked,
                ebay: document.getElementById('platform-ebay').checked,
                vinted: document.getElementById('platform-vinted').checked,
                mydealz: document.getElementById('platform-mydealz').checked,
                amazon: document.getElementById('platform-amazon').checked,
                hardwareschotte: document.getElementById('platform-hardwareschotte').checked
            };
            
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
                blacklist: blacklist,
                platforms: platforms
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

        function escapeHtml(value) { return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c])); }
        
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
                        <td class="px-4 py-3"><span class="px-2 py-1 rounded text-xs bg-slate-800 text-slate-300">${escapeHtml(item.platform)}</span></td>
                        <td class="px-4 py-3 font-medium text-white max-w-[150px] md:max-w-md truncate" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</td>
                        <td class="px-4 py-3 font-bold text-white text-right">${item.price.toFixed(2)} €</td>
                        <td class="px-4 py-3 ${diffColor} text-right font-semibold">${item.diff > 0 ? '+' : ''}${item.diff.toFixed(1)}%</td>
                        <td class="px-4 py-3 text-center">
                            <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" class="p-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 inline-block"><i class="fa-solid fa-arrow-up-right-from-square"></i></a>
                        </td>
                    </tr>
                `;
            }).join('');
        }
    </script>
</body>
</html>
"""
