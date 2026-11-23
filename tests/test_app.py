"""Tests for the refactored Marketplace Price Scout.

Run with::

    pytest -q            # or: python -m pytest -q

The tests never touch the network: HTTP clients are replaced by stubs and the
adapter registry is patched where a platform's transport is not under test.
"""
from __future__ import annotations

import logging
import time
import unittest
from unittest.mock import Mock, patch

from marketplace_price_scout import app as app_module
from marketplace_price_scout.app import create_app
from marketplace_price_scout.config import PLATFORM_NAMES, ScoutConfig
from marketplace_price_scout.logging_terminal import (
    clear_terminal,
    get_log_snapshot,
    get_terminal_logs,
)
from marketplace_price_scout.scrapers import adapters
from marketplace_price_scout.scrapers.adapters import (
    PlatformBlocked,
    PlatformTimeout,
    ScraperError,
    calculate_trimmed_mean,
    clean_price,
    fetch,
    get_hardwareschotte_index,
    resolve_platforms,
    scrape_all_platforms,
    scrape_amazon,
)
from marketplace_price_scout.scrapers.validation import validate_input, validate_platforms

LOGGER = logging.getLogger("test")
AMAZON_HTML = (
    '<div data-component-type="s-search-result">'
    '<h2><a href="/dp/X"><span>Phone</span></a></h2>'
    '<span class="a-price"><span class="a-offscreen">€ 99,00</span></span>'
    "</div>"
)


def make_config(**overrides) -> ScoutConfig:
    """Config with retries/delays disabled so tests stay fast."""
    defaults = dict(max_retries=0, retry_backoff=0.0, rate_limit_delay=0.0, warmup_cookies=False)
    defaults.update(overrides)
    return ScoutConfig(**defaults)


def fake_response(status: int = 200, text: str = "", headers=None):
    response = Mock()
    response.status_code = status
    response.text = text
    response.headers = headers or {}
    return response


class ValidationTests(unittest.TestCase):
    def test_missing_blacklist_defaults_to_empty(self):
        self.assertEqual(validate_input("phone", 0, 10, None)[3], [])
        self.assertEqual(validate_input("phone", 0, 10, [None, " "])[3], [])

    def test_validation_rejects_nonfinite_and_bad_blacklist(self):
        for args in [
            ("phone", float("nan"), 10, []),
            ("phone", 0, float("inf"), []),
            ("phone", 0, 10, [{"a": 1}]),
            ("phone", [1], 10, []),
            ("", 0, 10, []),
            (None, 0, 10, []),
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_input(*args)

    def test_query_and_blacklist_normalization(self):
        self.assertEqual(
            validate_input(" phone ", 0, 10, [" bad "]), ("phone", 0.0, 10.0, ["bad"])
        )
        # internal whitespace is collapsed, comma strings are accepted
        self.assertEqual(
            validate_input("iphone   15  pro", 0, 10, "hülle, defekt")[0], "iphone 15 pro"
        )
        self.assertEqual(validate_input("x", 0, 10, "a, b")[3], ["a", "b"])

    def test_price_bounds(self):
        with self.assertRaises(ValueError):
            validate_input("x", 10, 5, [])
        with self.assertRaises(ValueError):
            validate_input("x", -1, 5, [])
        with self.assertRaises(ValueError):
            validate_input("x", 0, 10_000_001, [])
        # numeric strings from JSON are tolerated
        self.assertEqual(validate_input("x", "0", "10", [])[1:3], (0.0, 10.0))

    def test_platform_selection_validation(self):
        self.assertEqual(validate_platforms(None), {})
        self.assertEqual(validate_platforms({"EBAY": True}), {"ebay": True})
        self.assertEqual(validate_platforms({"vinted": "false"}), {"vinted": False})
        with self.assertRaises(ValueError):
            validate_platforms(["ebay"])
        with self.assertRaises(ValueError):
            validate_platforms({"ebayy": True})

    def test_price_parser_formats(self):
        cases = {
            "1.299,99 €": 1299.99,
            "99 €": 99.0,
            "1,299.99": 1299.99,
            "1.299 €": 1299.0,
            "89,-": 89.0,
            "10 - 20 €": 10.0,
            "Preis auf Anfrage": 0.0,
            "": 0.0,
            "VB": 0.0,
            "1.234.567,89 €": 1234567.89,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertAlmostEqual(clean_price(raw), expected, places=2)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        cfg = ScoutConfig()
        self.assertEqual(cfg.port, 5000)
        self.assertTrue(cfg.platforms["kleinanzeigen"])
        self.assertFalse(cfg.debug)
        self.assertEqual(set(cfg.platforms), set(PLATFORM_NAMES))

    def test_bogus_values_are_clamped(self):
        cfg = ScoutConfig(timeout=0, max_retries=99, max_results=0, trim_percent=5)
        self.assertGreaterEqual(cfg.timeout, 1.0)
        self.assertLessEqual(cfg.max_retries, 5)
        self.assertGreaterEqual(cfg.max_results, 1)
        self.assertLessEqual(cfg.trim_percent, 0.49)

    def test_short_user_agent_is_replaced(self):
        cfg = ScoutConfig(user_agent="Mozilla/5.0")
        self.assertIn("Chrome", cfg.user_agent)

    @patch.dict(
        "os.environ",
        {"API_LOG_RATE_LIMIT_PER_MINUTE": "600", "SCRAPER_TIMEOUT": "not-a-number"},
        clear=False,
    )
    def test_env_overrides_and_bad_env_fallback(self):
        cfg = ScoutConfig.from_env(config_path="/nonexistent/config.json")
        self.assertEqual(cfg.log_rate_limit_per_minute, 600)
        self.assertEqual(cfg.timeout, 15.0)


class AdapterTests(unittest.TestCase):
    def test_amazon_parse_and_reject_external_link(self):
        scraper = Mock()
        scraper.get.return_value = fake_response(200, AMAZON_HTML)
        items = scrape_amazon("phone", 0, 200, [], scraper, make_config(), LOGGER)
        self.assertEqual(items[0]["price"], 99.0)
        self.assertEqual(items[0]["url"], "https://www.amazon.de/dp/X")

        evil = AMAZON_HTML.replace('href="/dp/X"', 'href="https://evil.example/dp/X"')
        scraper.get.return_value = fake_response(200, evil)
        self.assertEqual(scrape_amazon("phone", 0, 200, [], scraper, make_config(), LOGGER), [])

    def test_406_is_an_error_not_an_empty_result(self):
        """The Vinted symptom: HTTP 406 used to be logged and swallowed."""
        scraper = Mock()
        scraper.get.return_value = fake_response(406)
        with self.assertRaises(PlatformBlocked) as ctx:
            adapters.scrape_vinted("iphone", 0, 1200, [], scraper, make_config(), LOGGER)
        self.assertEqual(ctx.exception.status_code, 406)

    def test_503_is_an_error_not_an_empty_result(self):
        """The Amazon symptom: HTTP 503 used to be logged and swallowed."""
        scraper = Mock()
        scraper.get.return_value = fake_response(503)
        with self.assertRaises(ScraperError) as ctx:
            scrape_amazon("iphone", 0, 1200, [], scraper, make_config(), LOGGER)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_retries_and_backoff_on_5xx(self):
        cfg = make_config(max_retries=2, retry_backoff=0.0)
        scraper = Mock()
        scraper.get.side_effect = [
            fake_response(503),
            fake_response(503),
            fake_response(200, AMAZON_HTML),
        ]
        with patch.object(adapters.time, "sleep") as sleep:
            items = scrape_amazon("phone", 0, 200, [], scraper, cfg, LOGGER)
        self.assertEqual(len(items), 1)
        self.assertEqual(scraper.get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_retry_gives_up_after_max_retries(self):
        cfg = make_config(max_retries=1, retry_backoff=0.0)
        scraper = Mock()
        scraper.get.return_value = fake_response(503)
        with patch.object(adapters.time, "sleep"), self.assertRaises(ScraperError):
            scrape_amazon("phone", 0, 200, [], scraper, cfg, LOGGER)
        self.assertEqual(scraper.get.call_count, 2)

    def test_non_retryable_status_is_not_retried(self):
        cfg = make_config(max_retries=3, retry_backoff=0.0)
        scraper = Mock()
        scraper.get.return_value = fake_response(404)
        with self.assertRaises(ScraperError):
            scrape_amazon("phone", 0, 200, [], scraper, cfg, LOGGER)
        self.assertEqual(scraper.get.call_count, 1)

    def test_timeout_maps_to_platform_timeout(self):
        import requests

        scraper = Mock()
        scraper.get.side_effect = requests.Timeout()
        with self.assertRaises(PlatformTimeout):
            fetch(
                "https://www.amazon.de/s?k=x",
                scraper,
                make_config(),
                "Amazon",
                LOGGER,
            )

    def test_retry_after_header_is_honoured(self):
        cfg = make_config(max_retries=1, retry_backoff=0.0)
        scraper = Mock()
        scraper.get.side_effect = [
            fake_response(429, headers={"Retry-After": "2"}),
            fake_response(200, "ok"),
        ]
        with patch.object(adapters.time, "sleep") as sleep:
            fetch("https://www.amazon.de/s?k=x", scraper, cfg, "Amazon", LOGGER)
        self.assertGreaterEqual(sleep.call_args[0][0], 2.0)

    def test_requests_headers_include_full_user_agent(self):
        with patch.object(adapters, "_warm_up"), patch.object(
            adapters, "reset_sessions"
        ):
            adapters.reset_sessions()
            cfg = make_config(use_curl_cffi=False)
            session = adapters.get_scraper(cfg, "vinted")
            self.assertIn("Chrome", session.headers["User-Agent"])
            self.assertEqual(session.headers["Accept-Language"], "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7")
            adapters.reset_sessions()

    def test_trimmed_mean(self):
        items = [{"price": p} for p in (10, 20, 30, 1000)]
        self.assertAlmostEqual(calculate_trimmed_mean(items, trim_percent=0.25), 25.0)
        self.assertEqual(calculate_trimmed_mean([]), 0.0)
        self.assertAlmostEqual(calculate_trimmed_mean([{"price": 10}, {"price": 20}]), 15.0)

    def test_hardwareschotte_failure_never_raises(self):
        scraper = Mock()
        scraper.get.return_value = fake_response(503)
        self.assertIsNone(
            get_hardwareschotte_index("iphone", scraper, make_config(), LOGGER)
        )


class OrchestrationTests(unittest.TestCase):
    def test_only_selected_platforms_are_contacted(self):
        contacted: list[str] = []

        def recorder(name):
            def _fn(*args, **kwargs):
                contacted.append(name)
                return []

            return _fn

        cfg = make_config()
        selection = {name: False for name in PLATFORM_NAMES}
        selection["kleinanzeigen"] = True
        with patch.dict(
            adapters.ADAPTERS,
            {name: recorder(name) for name in ("kleinanzeigen", "ebay", "vinted", "mydealz", "amazon")},
        ), patch.object(adapters, "get_scraper", return_value=object()):
            report = scrape_all_platforms("iphone", 0, 100, [], cfg, LOGGER, selection=selection)
        self.assertEqual(contacted, ["kleinanzeigen"])
        self.assertFalse(report.all_failed)
        skipped = {o.platform for o in report.outcomes if o.skipped}
        self.assertEqual(skipped, {"ebay", "vinted", "mydealz", "amazon", "hardwareschotte"})

    def test_config_disabled_platform_is_never_contacted(self):
        contacted: list[str] = []

        def recorder(name):
            def _fn(*args, **kwargs):
                contacted.append(name)
                return []

            return _fn

        cfg = make_config()
        cfg.platforms["vinted"] = False
        cfg.platforms["amazon"] = False
        with patch.dict(
            adapters.ADAPTERS,
            {name: recorder(name) for name in ("kleinanzeigen", "ebay", "vinted", "mydealz", "amazon")},
        ), patch.object(adapters, "get_scraper", return_value=object()):
            scrape_all_platforms("iphone", 0, 100, [], cfg, LOGGER, selection={"vinted": True})
        self.assertNotIn("vinted", contacted)
        self.assertNotIn("amazon", contacted)

    def test_all_failed_flag(self):
        def boom(*args, **kwargs):
            raise PlatformBlocked("Vinted", "blocked (HTTP 406)", 406)

        cfg = make_config()
        cfg.platforms["hardwareschotte"] = False
        with patch.dict(
            adapters.ADAPTERS, {name: boom for name in PLATFORM_NAMES if name != "hardwareschotte"}
        ), patch.object(adapters, "get_scraper", return_value=object()):
            report = scrape_all_platforms("iphone", 0, 100, [], cfg, LOGGER)
        self.assertTrue(report.all_failed)
        self.assertEqual(len(report.failed), 5)
        self.assertEqual({o.status_code for o in report.failed}, {406})

    def test_scrape_is_parallel(self):
        """Five platforms that each sleep must finish in roughly one sleep."""

        def slow(*args, **kwargs):
            time.sleep(0.4)
            return []

        cfg = make_config(scrape_deadline=5.0)
        with patch.dict(adapters.ADAPTERS, {name: slow for name in PLATFORM_NAMES}), patch.object(
            adapters, "get_scraper", return_value=object()
        ):
            started = time.monotonic()
            scrape_all_platforms("iphone", 0, 100, [], cfg, LOGGER)
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1.5)

    def test_deadline_abandons_slow_platform(self):
        def slow(*args, **kwargs):
            time.sleep(1.5)
            return []

        def fast(*args, **kwargs):
            return []

        cfg = make_config(scrape_deadline=0.5)
        registry = {name: fast for name in PLATFORM_NAMES}
        registry["vinted"] = slow
        with patch.dict(adapters.ADAPTERS, registry), patch.object(
            adapters, "get_scraper", return_value=object()
        ):
            report = scrape_all_platforms("iphone", 0, 100, [], cfg, LOGGER)
        self.assertTrue(report.deadline_exceeded)
        timed_out = [o for o in report.outcomes if "deadline" in (o.error or "")]
        self.assertEqual([o.platform for o in timed_out], ["vinted"])
        self.assertFalse(report.all_failed)

    def test_fetch_passes_explicit_timeout_and_headers(self):
        scraper = Mock()
        scraper.get.return_value = fake_response(200, "ok")
        cfg = make_config(timeout=7.0)
        fetch(
            "https://www.amazon.de/s?k=x",
            scraper,
            cfg,
            "Amazon",
            LOGGER,
            referer="https://www.amazon.de/",
        )
        kwargs = scraper.get.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 7.0)
        self.assertTrue(kwargs["allow_redirects"])
        self.assertEqual(kwargs["headers"]["Referer"], "https://www.amazon.de/")

    def test_resolve_platforms_intersection(self):
        cfg = make_config()
        cfg.platforms["vinted"] = False
        resolved = resolve_platforms(cfg, {"vinted": True, "ebay": True})
        self.assertFalse(resolved["vinted"])  # config wins
        self.assertTrue(resolved["ebay"])


class ApiTests(unittest.TestCase):
    """End-to-end behaviour of POST /api/scrape via the Flask test client."""

    def setUp(self):
        self.config = make_config()
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.outbound: list[str] = []

        def stub_scraper(cfg, platform=None, logger=None):
            self.outbound.append(platform or "?")
            return object()

        self._get_patch = patch.object(adapters, "get_scraper", side_effect=stub_scraper)
        self._get_patch.start()
        self.addCleanup(self._get_patch.stop)

        # Hardwareschotte is keyword-only in the app module; stub it so these
        # tests never touch the network.
        self._hs_patch = patch.object(app_module, "get_hardwareschotte_index", return_value=None)
        self._hs_patch.start()
        self.addCleanup(self._hs_patch.stop)
        clear_terminal()

    def _set_registry(self, mapping):
        patcher = patch.dict(adapters.ADAPTERS, mapping)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post(self, **payload):
        payload.setdefault("query", "iphone")
        return self.client.post("/api/scrape", json=payload)

    def test_disabled_platforms_are_not_scraped_and_do_not_show_as_results(self):
        contacted: list[str] = []

        def recorder(name):
            def _fn(*args, **kwargs):
                contacted.append(name)
                return []

            return _fn

        self._set_registry({n: recorder(n) for n in PLATFORM_NAMES})
        response = self._post(
            minPrice=400,
            maxPrice=1200,
            platforms={n: n == "kleinanzeigen" for n in PLATFORM_NAMES},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(contacted, ["kleinanzeigen"])
        body = response.get_json()
        self.assertIn("No matching offers found.", body["message"])
        skipped = {p["platform"] for p in body["platforms"] if p["skipped"]}
        self.assertEqual(skipped, {"eBay", "Vinted", "mydealz", "Amazon", "Hardwareschotte"})
        self.assertNotIn("Kleinanzeigen", skipped)
        self.assertNotIn("amazon: blocked", " ".join(body["warnings"]))

    def test_all_platforms_blocked_returns_5xx_not_200(self):
        def blocked(name, code):
            def _fn(*args, **kwargs):
                raise PlatformBlocked(name, f"blocked (HTTP {code})", code)

            return _fn

        self._set_registry({n: blocked(n, 503) for n in PLATFORM_NAMES})
        response = self._post(minPrice=400, maxPrice=1200)
        self.assertEqual(response.status_code, 503)
        body = response.get_json()
        self.assertIn("error", body)
        self.assertEqual(len(body["warnings"]), 5)

    def test_vinted_406_alone_does_not_fail_the_whole_search(self):
        self._set_registry(
            {
                "kleinanzeigen": lambda *a, **k: [
                    {"platform": "Kleinanzeigen", "title": "iPhone 15 Pro", "price": 800.0, "url": "https://www.kleinanzeigen.de/s-anzeige/x"}
                ],
                "ebay": lambda *a, **k: [],
                "vinted": lambda *a, **k: (_ for _ in ()).throw(
                    PlatformBlocked("Vinted", "blocked (HTTP 406)", 406)
                ),
                "mydealz": lambda *a, **k: [],
                "amazon": lambda *a, **k: (_ for _ in ()).throw(
                    PlatformBlocked("Amazon", "blocked (HTTP 503)", 503)
                ),
            }
        )
        response = self._post(minPrice=400, maxPrice=1200)
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["price"], 800.0)
        self.assertTrue(any("Vinted" in w for w in body["warnings"]))
        self.assertTrue(any("Amazon" in w for w in body["warnings"]))

    def test_no_result_platform_selected_is_client_error(self):
        self._set_registry({n: lambda *a, **k: [] for n in PLATFORM_NAMES})
        response = self._post(
            platforms={n: n == "hardwareschotte" for n in PLATFORM_NAMES}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No result platform was selected", response.get_json()["message"])
        self.assertEqual(self.outbound, [])

    def test_invalid_input_returns_400_not_500(self):
        payloads = [
            {"query": "", "minPrice": 0, "maxPrice": 10},
            {"query": "x", "minPrice": [1], "maxPrice": 10},
            {"query": "x", "minPrice": 0, "maxPrice": 10, "blacklist": [{"a": 1}]},
            {"query": "x", "minPrice": 0, "maxPrice": 10, "platforms": ["ebay"]},
            {"query": "x", "minPrice": 100, "maxPrice": 10},
            {"query": "x", "minPrice": 0, "maxPrice": 10, "platforms": {"ebayy": True}},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post("/api/scrape", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())

    def test_all_platforms_timeout_returns_503(self):
        def slow(*args, **kwargs):
            raise PlatformTimeout("Vinted", "timeout after 15s")

        self._set_registry({n: slow for n in PLATFORM_NAMES})
        self.config.scrape_deadline = 5.0
        response = self._post()
        self.assertEqual(response.status_code, 503)
        self.assertTrue(any("timeout" in w for w in response.get_json()["warnings"]))

    def test_missing_json_body_returns_400(self):
        response = self.client.post("/api/scrape", data="not json", content_type="text/plain")
        self.assertEqual(response.status_code, 400)

    def test_response_contract(self):
        self._set_registry({n: lambda *a, **k: [] for n in PLATFORM_NAMES})
        body = self._post(minPrice=0, maxPrice=100).get_json()
        for key in ("items", "avgPrice", "indexPrice", "count", "platforms", "warnings"):
            self.assertIn(key, body)


class LogEndpointTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config()
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        clear_terminal()

    def test_logs_include_cursor_for_incremental_polling(self):
        log = logging.getLogger("marketplace_price_scout")
        log.info("first line")
        log.info("second line")

        first = self.client.get("/api/logs").get_json()
        self.assertIn("latestSeq", first)
        self.assertTrue(any("second line" in line for line in first["logs"]))

        cursor = first["latestSeq"]
        log.info("third line")
        delta = self.client.get(f"/api/logs?since={cursor}").get_json()
        self.assertEqual(len(delta["logs"]), 1)
        self.assertIn("third line", delta["logs"][0])
        self.assertGreater(delta["latestSeq"], cursor)

    def test_since_in_future_returns_empty(self):
        body = self.client.get("/api/logs?since=999999").get_json()
        self.assertEqual(body["logs"], [])

    def test_invalid_query_params_return_400(self):
        self.assertEqual(self.client.get("/api/logs?since=abc").status_code, 400)
        self.assertEqual(self.client.get("/api/logs?limit=abc").status_code, 400)

    def test_logs_are_not_cached_by_the_browser(self):
        response = self.client.get("/api/logs")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_clear_endpoint(self):
        logging.getLogger("marketplace_price_scout").info("to be removed")
        response = self.client.post("/api/logs/clear")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.get_json()["removed"], 1)
        self.assertEqual(self.client.get("/api/logs").get_json()["logs"], [])

    def test_log_polling_does_not_hit_the_rate_limit(self):
        """Regression for the 429 storm: 1s polling for a minute must work."""
        statuses = {self.client.get("/api/logs").status_code for _ in range(45)}
        self.assertEqual(statuses, {200})

    def test_scrape_rate_limit_still_applies(self):
        with patch.object(app_module, "scrape_all_platforms") as scrape:
            scrape.return_value = adapters.ScrapeReport()
            statuses = [
                self.client.post(
                    "/api/scrape",
                    json={"query": "x", "minPrice": 0, "maxPrice": 10, "platforms": {"ebay": True}},
                ).status_code
                for _ in range(self.config.api_rate_limit_per_minute + 2)
            ]
        self.assertIn(429, statuses)
        response = self.client.post(
            "/api/scrape",
            json={"query": "x", "minPrice": 0, "maxPrice": 10, "platforms": {"ebay": True}},
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
        self.assertIn("error", response.get_json())


class LogBufferTests(unittest.TestCase):
    def setUp(self):
        clear_terminal()

    def test_snapshot_shape(self):
        logging.getLogger("marketplace_price_scout").info("hello")
        snapshot = get_log_snapshot(limit=10)
        self.assertIn("hello", " ".join(snapshot["logs"]))
        self.assertEqual(snapshot["truncated"], False)

    def test_limit_and_newest_first(self):
        log = logging.getLogger("marketplace_price_scout")
        for index in range(5):
            log.info("line-%s", index)
        logs = get_terminal_logs(limit=2)
        self.assertEqual(len(logs), 2)
        self.assertIn("line-4", logs[0])


if __name__ == "__main__":
    unittest.main()
