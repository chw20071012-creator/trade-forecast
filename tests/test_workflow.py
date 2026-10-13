"""A complete local demo proves the modules work together without live sends."""
import time
from decimal import Decimal

from fastapi.testclient import TestClient
from trade_agent.app import create_app
from trade_agent.config import Config


def test_complete_demo_workflow(tmp_path):
    config = Config(tmp_path, "workflow-test-" + "x" * 48)
    app = create_app(config)
    headers = {"Authorization": "Bearer " + config.api_key}
    with TestClient(app, base_url="http://127.0.0.1:8765", headers=headers) as client:
        def post(path, data=None):
            response = client.post(path, json=data or {})
            assert response.status_code == 200, (path, response.text)
            return response.json()

        def finish(task):
            for _ in range(200):
                response = client.get("/api/tasks/" + task["id"])
                assert response.status_code == 200
                status = response.json()
                if status["state"] in {"completed", "failed"}:
                    assert status["state"] == "completed", status
                    return status["result"]
                time.sleep(0.01)
            raise AssertionError("Local demo task did not finish")

        loaded = post("/api/demo/load")
        assert loaded["demo"] and loaded["counts"]["customers"] == 4
        analysis = finish(post("/api/markets/analyze", {"source": "demo", "hs_codes": ["4202", "0902"]}))
        assert analysis["demo"] and analysis["candidates"]
        assert all(c["demo"] for c in analysis["candidates"])
        post("/api/markets/select", {"country": "Germany"})
        leads = finish(post("/api/acquisition/search", {"source": "demo", "country": "Germany", "max_results": 1}))
        assert leads

        customers = client.get("/api/entities/customers").json()
        customer = next(c for c in customers if c["id"] == "demo-customer-bags-shop")
        assert customer["company_size"] == "micro"
        product_id = "demo-product-weekend-bag"
        rule = post("/api/profit-rules", {"business": "bags", "product_id": product_id,
                    "proposed_min_margin": "0.15", "suggested_margin": "0.25",
                    "rationale": "演示：利润假设用于功能验证，不是行情结论", "evidence": [{"source": "synthetic demo"}]})
        assert not rule["confirmed"]
        post("/api/profit-rules/" + rule["id"] + "/confirm")
        costs = [
            {"name": name, "category": category, "amount": amount, "currency": "USD", "basis": "per_unit", "confirmed": True}
            for name, category, amount in [
                ("演示采购", "purchase", "10"), ("演示包装", "packaging", "1"),
                ("演示检测", "testing", "0"), ("EXW不含运输", "freight", "0"),
                ("演示收款费", "payment", "0.2"), ("演示服务成本", "service", "0.5")
            ]
        ]
        quote = post("/api/quotes", {"product_id": product_id, "quantity": "60", "currency": "USD", "terms": "EXW", "profit_rule_id": rule["id"], "cost_items": costs})
        assert quote["usable"] and quote["demo"]
        assert Decimal(quote["suggested_price"]) >= Decimal(quote["floor_price"]) >= Decimal("13.76")

        draft = post("/api/mail/drafts", {"customer_id": customer["id"], "to": customer["email"],
            "subject": "[DEMO] Small-batch weekend bags for your travel shop",
            "body": "This is a demo only. Your synthetic travel-shop profile lists weekend bags. Shall we confirm the material, logo and quantity before a sample quotation?",
            "evidence": [{"fact": "Synthetic travel-shop profile lists weekend bags", "source": "demo/data.json"}],
            "personalization_notes": "Matches this independent retailer's weekend-bag assortment and small batch needs."})
        batch = post("/api/mail/approve", {"drafts": [{"id": draft["id"], "version": draft["version"]}], "confirmed": True})
        sent = finish(post("/api/mail/batches/" + batch["id"] + "/send"))
        assert sent["state"] == "completed"
        final_draft = client.get("/api/entities/mail_drafts/" + draft["id"]).json()
        assert final_draft["state"] == "simulated" and final_draft["mode"] == "demo"

        wa = post("/api/whatsapp", {"customer_id": customer["id"], "phone": "+491234567890", "text": "[DEMO] Weekend-bag sample enquiry; not a real message.",
            "evidence": [{"fact": "Synthetic retailer sells travel bags", "source": "demo/data.json"}], "personalization_notes": "Small-batch travel-shop question"})
        assert wa
        post("/api/whatsapp/" + wa["id"] + "/status", {"status": "sent", "confirmed": True})

        order = post("/api/orders", {"customer_id": customer["id"], "quote_id": quote["id"], "currency": "USD", "terms": "EXW",
            "lines": [{"product_id": product_id, "description": "DEMO 600D weekend bag", "quantity": "60", "unit": quote["unit"], "unit_price": quote["suggested_price"], "net_weight": "35", "gross_weight": "42", "packages": "3"}],
            "seller": {"name": "DEMO Seller", "address": "Synthetic seller address"},
            "buyer": {"name": customer["name"], "address": "Synthetic buyer address"}, "po_number": "DEMO-PO-TEST"})
        update = post("/api/order-updates", {"order_id": order["id"], "stage": "production", "patch": {"status": "in_progress", "completion_percent": 80}, "source": "email"})
        pending = client.get("/api/entities/orders/" + order["id"]).json()
        assert pending["stages"]["production"]["status"] == "not_started"
        post("/api/order-updates/" + update["id"] + "/confirm")
        production = client.get("/api/entities/orders/" + order["id"]).json()
        assert production["stages"]["production"]["completion_percent"] == "80"

        receipt = post("/api/order-updates", {"order_id": order["id"], "stage": "receipts", "source": "email", "patch": {"status": "verified", "verified_amount": order["total"], "currency": "USD", "bank_verified": True}})
        post("/api/order-updates/" + receipt["id"] + "/confirm")
        updated_order = client.get("/api/entities/orders/" + order["id"]).json()
        assert updated_order["stages"]["receipts"]["status"] == "claimed"
        docs = post("/api/orders/" + order["id"] + "/documents")
        assert len(docs["files"]) == 5
        for file in docs["files"]:
            response = client.get(file["download_url"])
            assert response.status_code == 200 and len(response.content) > 100
        consistency = post("/api/documents/verify", {"order_id": order["id"]})
        assert consistency["status"] == "consistent", consistency
        followup = post("/api/followups", {"days": 7})
        assert followup
        backup = post("/api/backup")
        assert not backup["includes_credentials"]
        assert client.get(backup["files"][0]["download_url"]).status_code == 200
        schema = client.get("/openapi-actions.json").json()
        assert config.api_key not in str(schema)
        assert len([1 for p in schema["paths"].values() for m in p if m in {"get", "post", "patch", "delete"}]) <= 30
