"""Data integrity boundaries; no network or fabricated live-success tests."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from trade_agent.acquisition import AcquisitionService, _public_url
from trade_agent.market import MarketService, normalize_record


class MemoryStore:
    def __init__(self):
        self.records, self.preferences, self.events = {}, {"demo_mode": True}, []
        self.lock = threading.RLock()
        self.data_dir = Path(tempfile.gettempdir())

    def put(self, kind, data, record_id=None):
        bucket = self.records.setdefault(kind, {})
        record_id = record_id or f"{kind}_{len(bucket) + 1}"
        record = dict(copy.deepcopy(data), id=record_id)
        bucket[record_id] = record
        return copy.deepcopy(record)

    def get(self, kind, record_id):
        return copy.deepcopy(self.records[kind][record_id])

    def list(self, kind, limit=5000):
        return copy.deepcopy(list(self.records.get(kind, {}).values())[:limit])

    def settings(self):
        return dict(self.preferences)

    def update_settings(self, patch):
        self.preferences.update(patch)
        return self.settings()

    def event(self, action, details):
        self.events.append((action, details))


def statistic(**overrides):
    return dict({"reporter": "Germany", "partner": "World", "flow": "import",
                 "period": "2024", "hs_code": "0902", "hs_version": "HS2017",
                 "value": 1000, "currency": "USD", "source": "official_test_fixture",
                 "complete_period": True, "coverage": "complete", "demo": False}, **overrides)


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.market = MarketService(self.store)

    def test_statistics_do_not_fabricate_missing_or_divide_by_zero(self):
        row = normalize_record(statistic(value=None, quantity=0, quantity_unit="kg"))
        self.assertIsNone(row["value"])
        self.assertIsNone(row["unit_value"])
        weight_only = normalize_record(statistic(net_weight_kg=20))
        self.assertEqual(weight_only["weight_unit_value"], 50)
        self.assertIsNone(weight_only["unit_value"])
        self.assertIn("SKU", weight_only["unit_value_warning"])

    def test_no_currency_assumption_and_no_lost_hs_leading_zero(self):
        with self.assertRaises(ValueError):
            normalize_record(statistic(currency=""))
        with self.assertRaises(ValueError):
            normalize_record(statistic(hs_code=902))
        self.assertEqual(normalize_record(statistic())["hs_code"], "0902")

    def test_reimport_updates_instead_of_doubling_market(self):
        self.market.import_records([statistic()])
        self.market.import_records([statistic(value=1100)])
        self.assertEqual(len(self.store.list("market_records")), 1)
        result = self.market.analyze({})
        self.assertEqual(result["candidates"][0]["latest_value"], 1100)

    def test_world_bilateral_parent_child_and_versions_not_added(self):
        self.market.import_records([
            statistic(value=1000), statistic(hs_code="090210", value=600),
            statistic(partner="China", value=300),
            statistic(hs_version="HS2022", value=1200),
            statistic(reporter="China", partner="Germany", flow="export", value=290),
            statistic(currency="EUR", value=900),
        ])
        candidates = self.market.analyze({"hs_code": "0902"})["candidates"]
        self.assertEqual(len(candidates), 5)
        self.assertEqual(sorted(c["latest_value"] for c in candidates), [290, 600, 900, 1000, 1200])

    def test_growth_requires_complete_comparable_years(self):
        self.market.import_records([statistic(period="2022", value=100),
                                    statistic(period="2023", value=120),
                                    statistic(period="2024", value=5, complete_period=False)])
        candidate = self.market.analyze({})["candidates"][0]
        self.assertEqual(candidate["latest_value"], 5)
        self.assertEqual(candidate["growth_periods"], ["2022", "2023"])
        self.assertAlmostEqual(candidate["growth_percent"], 20)
        self.assertIn("统计期完整性未核验", candidate["missing"])

    def test_demo_and_real_statistics_are_isolated(self):
        self.market.import_records([statistic(value=1000), statistic(value=99999, demo=True)])
        self.assertEqual(self.market.analyze({})["candidates"][0]["latest_value"], 1000)
        self.assertEqual(self.market.analyze({"source": "demo"})["candidates"][0]["latest_value"], 99999)

    def test_failed_preview_does_not_save_zero_or_claim_connection(self):
        with patch("trade_agent.market.httpx.Client.get", side_effect=__import__("httpx").ConnectError("offline")):
            result = self.market.fetch_comtrade({"hs_codes": ["0902"], "year": "2024", "countries": ["Germany"]})
        self.assertEqual(result["status"], "unconnected")
        self.assertEqual(result["records"], 0)
        self.assertEqual(self.store.list("market_records"), [])

    def test_statistics_file_import_units_formulas_and_china_export_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            self.store.data_dir = Path(temp) / "data"
            path = Path(temp) / "official.csv"
            path.write_text("报告国,贸易伙伴,贸易流向,年份,HS编码,HS版本,金额,币种,金额倍率,完整统计期,来源\n"
                            "中国,德国,出口,2024,0902,HS2017,12,USD,1000,TRUE,customs_export\n"
                            "中国,德国,出口,2023,0902,HS2017,=10*2,USD,1000,TRUE,customs_export\n", encoding="utf-8")
            result = self.market.import_file(path)
            self.assertEqual(result["accepted"], 1)
            self.assertEqual(result["rejected"], 1)
            self.assertFalse(result["formulas_executed"])
            self.assertTrue(Path(result["files"][0]).is_file())
            candidate = self.market.analyze({})["candidates"][0]
            self.assertEqual(candidate["country"], "Germany")
            self.assertEqual(candidate["scope"], "china_export_to_market")
            self.assertEqual(candidate["latest_value"], 12000)
            stored = self.store.list("market_records")[0]
            self.assertEqual(stored["source_row"], 2)
            self.assertEqual(stored["hs_code"], "0902")

    def test_xlsx_statistics_skip_instruction_sheets_without_inventing_scope(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as temp:
            self.store.data_dir = Path(temp) / "data"
            path = Path(temp) / "official.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "market_records"
            sheet.append(["reporter", "flow", "period", "hs_code", "value", "currency", "source"])
            sheet.append(["Germany", "import", "2024", "0902", 500, "USD", "official_export"])
            workbook.create_sheet("填写说明").append(["这些不是贸易数据"])
            workbook.save(path)
            result = self.market.import_file(path)
            self.assertEqual(result["accepted"], 1)
            self.assertEqual(result["rejected"], 0)
            stored = self.store.list("market_records")[0]
            self.assertIsNone(stored["partner"])
            self.assertIsNone(stored["complete_period"])
            self.assertEqual(self.market.analyze({})["status"], "no_comparable_data")


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.service = AcquisitionService(self.store)

    def test_no_prospecting_before_country_confirmation(self):
        with self.assertRaises(ValueError):
            self.service.search({"source": "import", "country": "Germany", "records": []})
        MarketService(self.store).select("德国")
        result = self.service.search({"source": "import", "country": "DE", "records": []})
        self.assertEqual(result["country"], "Germany")

    def test_all_small_leads_retained_beyond_display_batch(self):
        MarketService(self.store).select("Germany")
        result = self.service.search({"source": "import", "country": "Germany", "max_results": 1,
                                      "records": [{"name": "Tiny Tea Stall", "size": "sole_proprietor", "phone": "+49 1111111"},
                                                  {"name": "Small Bag Shop", "size": "small", "email": "owner@example.com"}]})
        self.assertEqual(result["retained_count"], 2)
        self.assertEqual(len(result["customers"]), 1)
        self.assertEqual(result["remaining_queued"], 1)
        self.assertEqual(len(self.store.list("customers")), 2)
        self.assertTrue(all(c["profitability"] == "unverified" for c in self.store.list("customers")))

    def test_branches_not_merged_and_suppression_survives_repeat_import(self):
        MarketService(self.store).select("Germany")
        records = [{"name": "Tea Brand", "website": "https://teabrand.example", "address": "Branch A"},
                   {"name": "Tea Brand", "website": "https://teabrand.example", "address": "Branch B"}]
        self.service.search({"source": "import", "records": records})
        first = self.store.list("customers")[0]
        first["lead_status"] = "suppressed"
        self.store.put("customers", first, first["id"])
        self.service.search({"source": "import", "records": records})
        self.assertEqual(len(self.store.list("customers")), 2)
        self.assertEqual(self.store.get("customers", first["id"])["lead_status"], "suppressed")

    def test_demo_never_enriched_and_real_import_cannot_accept_demo(self):
        customer = self.store.put("customers", {"name": "Synthetic", "demo": True, "website": "https://demo.invalid"})
        with patch.object(self.service, "_website_profile", side_effect=AssertionError("network should not run")):
            self.assertEqual(self.service.enrich(customer["id"])["status"], "demo")
        MarketService(self.store).select("Germany")
        result = self.service.search({"source": "import", "records": [dict(customer, country="Germany")]})
        self.assertEqual(len(result["errors"]), 1)

    def test_missing_contact_does_not_discard_a_customer(self):
        MarketService(self.store).select("Germany")
        result = self.service.search({"source": "import", "records": [{"name": "No Website Shop"}]})
        customer = result["customers"][0]
        self.assertEqual(customer["lead_status"], "needs_contact")
        self.assertEqual(self.service.enrich(customer["id"])["status"], "needs_website")
        self.assertEqual(len(self.store.list("customers")), 1)

    def test_exhibition_retains_all_candidates_without_claiming_organizer_is_buyer(self):
        MarketService(self.store).select("Germany")
        fixture = {"links": [{"url": "https://expo.example/about", "text": "Organizer", "page_url": "https://expo.example/list"},
                              {"url": "https://smallteashop.example/", "text": "Small Tea Shop", "page_url": "https://expo.example/list"},
                              {"url": "https://smallbags.example/", "text": "Small Bags", "page_url": "https://expo.example/list"},
                              {"url": "https://linkedin.com/company/expo", "text": "Follow us", "page_url": "https://expo.example/list"}]}
        with patch.object(self.service, "_website_profile", return_value=fixture):
            result = self.service.search({"source": "exhibitions", "urls": ["https://expo.example/list"],
                                          "max_results": 1, "enrich": False})
        self.assertEqual(result["retained_count"], 2)
        self.assertEqual(len(result["customers"]), 1)
        all_customers = self.store.list("customers")
        self.assertEqual({c["name"] for c in all_customers}, {"Small Tea Shop", "Small Bags"})
        self.assertTrue(all(c["procurement_status"] == "unverified" for c in all_customers))
        self.assertTrue(all(c["buyer_match_status"] == "needs_review" for c in all_customers))

    def test_public_fetch_never_accepts_local_network_or_credentials(self):
        for url in ("http://127.0.0.1/", "http://169.254.169.254/latest", "http://10.0.0.1/",
                    "http://localhost/", "http://internal.local/", "file:///etc/passwd",
                    "https://user:pass@example.com/", "http://example.com:8000/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _public_url(url, resolve=False)
        with patch("trade_agent.acquisition.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.8", 443))]):
            with self.assertRaises(ValueError):
                _public_url("https://public.example/")


if __name__ == "__main__":
    unittest.main()
