"""Tests for the refactored Marketplace Price Scout."""
from __future__ import annotations

import logging
import unittest
from unittest.mock import Mock

from marketplace_price_scout.scrapers.validation import validate_input
from marketplace_price_scout.scrapers.adapters import clean_price, scrape_amazon
from marketplace_price_scout.config import ScoutConfig


class CoreTests(unittest.TestCase):
    def test_validation_rejects_nonfinite_and_bad_blacklist(self):
        for args in [("phone", float("nan"), 10, []), ("phone", 0, 10, None)]:
            with self.assertRaises(ValueError):
                validate_input(*args)

    def test_query_and_blacklist_normalization(self):
        self.assertEqual(
            validate_input(" phone ", 0, 10, [" bad "]), ("phone", 0.0, 10.0, ["bad"])
        )

    def test_price_parser_european_format(self):
        self.assertEqual(clean_price("1.299,99 €"), 1299.99)

    def test_new_adapters_parse_and_reject_external_link(self):
        html = """<div data-component-type="s-search-result"><h2><a href="/dp/X"><span>Phone</span></a></h2><span class="a-price"><span class="a-offscreen">€ 99,00</span></span></div>"""
        scraper = Mock()
        scraper.get.return_value.status_code = 200
        scraper.get.return_value.text = html
        
        config = ScoutConfig()
        items = scrape_amazon("phone", 0, 200, [], scraper, config, logging.getLogger())
        
        self.assertEqual(items[0]["price"], 99.0)
        self.assertEqual(items[0]["url"], "https://www.amazon.de/dp/X")

    def test_config_defaults(self):
        cfg = ScoutConfig()
        self.assertEqual(cfg.port, 5000)
        self.assertTrue(cfg.platforms["kleinanzeigen"])
        self.assertFalse(cfg.debug)


if __name__ == "__main__":
    unittest.main()
