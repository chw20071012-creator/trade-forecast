from __future__ import annotations

import copy
import csv
import io
import ipaddress
import json
import os
import re
import secrets
import shutil
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import __version__
from .config import Config, ROOT
from .models import (
    ApprovalRequest, CompleteOAuth, CustomerRequest, DraftRequest, FollowupRequest,
    MarketRequest, OrderRequest, ProfitRequest, QuoteRequest, RecordsRequest,
    SearchRequest, SelectRequest, SyncRequest, UpdateRequest, WhatsAppRequest,
)
from .store import Store, now
from .tasks import TaskManager

READABLE = {
    "customers", "products", "market_records", "market_selections", "market_analyses",
    "acquisition_runs", "profit_rules", "quotes", "orders", "order_updates",
    "mail_drafts", "mail_batches", "email_messages", "inquiries", "whatsapp_drafts",
    "tasks", "imports", "import_observations", "followups", "documents", "files",
    "whatsapp_messages", "contact_suppressions",
}
MANUAL = {"customers", "products"}


def create_app(config: Config | None = None) -> FastAPI:
    from .acquisition import AcquisitionService
    from .market import MarketService
    from .mail import MailService
    from .business import BusinessService
    from .imports import ImportService

    config = config or Config.load()
    if (config.data_dir / ".restore.lock").exists():
        raise ValueError("资料恢复正在进行，请完成恢复后启动程序")
    store = Store(config.data_dir)
    tasks = TaskManager(store)
    acquisition, market = AcquisitionService(store), MarketService(store)
    mail = MailService(store, config.data_dir)
    business, imports = BusinessService(store), ImportService(store)
    store.update_settings({"mail_oauth_redirect_uri": f"http://127.0.0.1:{config.port}/api/mail/oauth/callback"})

    @asynccontextmanager
    async def lifespan(app):
        marker = config.data_dir / ".app.pid"
        marker.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        yield
        for batch in store.list("mail_batches"):
            if batch.get("state", batch.get("status")) in {"sending", "running", "waiting"}:
                try:
                    mail.pause_batch(batch["id"])
                except (ValueError, KeyError):
                    pass
        tasks.close()
        marker.unlink(missing_ok=True)

    app = FastAPI(title="AI 外贸工作台", version=__version__, lifespan=lifespan)
    app.state.store, app.state.config, app.state.tasks, app.state.mail = store, config, tasks, mail
    security = HTTPBearer(auto_error=False)

    def authenticated(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
        if not credentials or credentials.scheme.lower() != "bearer" or not secrets.compare_digest(credentials.credentials, config.api_key):
            raise HTTPException(401, "请输入本机接口密钥", headers={"WWW-Authenticate": "Bearer"})

    auth = [Depends(authenticated)]

    def require_local(request: Request):
        client = request.client.host if request.client else ""
        try:
            loopback = ipaddress.ip_address(client).is_loopback
        except ValueError:
            loopback = False
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        origin = request.headers.get("origin")
        origin_ok = not origin or (urlparse(origin).hostname in {"127.0.0.1", "localhost"} and urlparse(origin).port in {None, config.port})
        if not loopback or host not in {"127.0.0.1", "localhost"} or not origin_ok or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "此操作只能在电脑本机页面完成")

    def dump(model) -> dict:
        return model.model_dump(exclude_none=True)

    def safe_path(path: str | Path) -> Path:
        candidate = Path(path).resolve()
        if not candidate.is_relative_to(config.data_dir.resolve()) or not candidate.is_file():
            raise ValueError("文件不在本机资料目录内或不存在")
        if (config.data_dir / "secrets").resolve() in candidate.parents or candidate.name in {"trade.sqlite3", "trade.sqlite3-wal", "trade.sqlite3-shm"}:
            raise ValueError("认证文件和数据库不能作为业务附件下载")
        return candidate

    def register_file(path: str | Path) -> dict:
        candidate = safe_path(path)
        existing = next((f for f in store.list("files") if f.get("path") == str(candidate)), None)
        saved = existing or store.put("files", {"path": str(candidate), "name": candidate.name})
        return {"file_id": saved["id"], "name": saved["name"], "download_url": f"/api/files/{saved['id']}"}

    def outputs(result: Any) -> Any:
        if isinstance(result, list):
            return [outputs(item) for item in result]
        if isinstance(result, dict):
            result = dict(result)
            for key in list(result):
                if key != "files":
                    result[key] = outputs(result[key])
            files = result.get("files")
            if files:
                mapped = []
                values = files.values() if isinstance(files, dict) else files
                for entry in values:
                    path = entry if isinstance(entry, str) else entry.get("path")
                    if path:
                        mapped.append(register_file(path))
                    elif isinstance(entry, dict) and entry.get("file_id"):
                        mapped.append(entry)
                result["files"] = mapped
            return result
        return result

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)[:1500]})

    @app.exception_handler(KeyError)
    async def key_error(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)[:500]})

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path == "/":
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "application": "trade_agent", "version": __version__}

    @app.get("/", include_in_schema=False)
    def index():
        return HTMLResponse((ROOT / "static" / "index.html").read_text(encoding="utf-8"))

    @app.get("/local/bootstrap", include_in_schema=False)
    def bootstrap(request: Request):
        require_local(request)
        return {"api_key": config.api_key, "base_url": f"http://127.0.0.1:{config.port}"}

    @app.get("/api/status", dependencies=auth, summary="读取运行状态与各模块实际接入状态")
    def status():
        settings = store.settings()
        browser_root = Path(__import__("os").environ.get("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".runtime" / "browsers")))
        browser_present = (browser_root.exists() and any(browser_root.glob("chromium*"))) or bool(os.environ.get("TRADE_BROWSER_EXECUTABLE") and Path(os.environ["TRADE_BROWSER_EXECUTABLE"]).is_file())
        return {
            "version": __version__, "demo_mode": settings["demo_mode"],
            "counts": {kind: len(store.list(kind)) for kind in ["customers", "products", "quotes", "orders", "inquiries", "mail_drafts", "tasks"]},
            "settings": settings,
            "integrations": {
                "gmail": mail.status(),
                "maps": {"browser_installed": browser_present, "state": "ready_to_attempt" if browser_present else "browser_required", "live_verified": False, "note": "运行时核实网络和页面；已安装浏览器不等于已获客"},
                "official_statistics": {"state": "import_available", "live_verified": False, "note": "支持统计导入与 Comtrade 有限预览；当前官方站点连通尚未验证"},
                "chatgpt": {"public_url_configured": bool(settings.get("public_url")), "live_verified": False, "note": "需设置 HTTPS 入口并在 GPT Actions 完成一次实际调用"},
                "whatsapp": {"state": "manual_link", "note": "生成消息和链接；由你点击发送"},
            },
        }

    @app.get("/api/entities/{kind}", dependencies=auth, summary="读取客户、产品、草稿、询盘、订单或其他记录")
    def entities(kind: str, limit: int = Query(5000, ge=1, le=50000)) -> list[dict[str, Any]]:
        if kind not in READABLE:
            raise HTTPException(404, "不支持的资料类型")
        return store.list(kind, limit)

    @app.get("/api/entities/{kind}/{record_id}", dependencies=auth, summary="读取一条业务记录的完整内容")
    def entity(kind: str, record_id: str) -> dict[str, Any]:
        if kind not in READABLE:
            raise HTTPException(404, "不支持的资料类型")
        return store.get(kind, record_id)

    @app.post("/api/entities/{kind}", dependencies=auth, summary="录入或更新客户及用户提供的产品资料")
    def manual(kind: str, data: dict[str, Any] = Body(...)):
        if kind not in MANUAL:
            raise ValueError("只能直接录入 customers 或 products；审批与订单请使用对应接口")
        if not data.get("name") and not data.get("company_name") and not data.get("product_name"):
            raise ValueError("请填写客户或产品名称")
        result = store.put(kind, data, data.get("id"))
        store.event("manual_record", {"kind": kind, "id": result["id"]})
        return result

    @app.get("/api/settings", dependencies=auth, summary="读取可修改的业务配置")
    def settings_get():
        return store.settings()

    @app.patch("/api/settings", dependencies=auth, summary="修改本机业务配置")
    def settings_patch(patch: dict[str, Any] = Body(...)):
        if any(re.search(r"secret|token|password|api_key", key, re.I) for key in patch):
            raise ValueError("认证信息请配置到本机 secrets 目录，不写入业务设置")
        for key in ("demo_mode", "mail_policy_reviewed"):
            if key in patch and not isinstance(patch[key], bool):
                raise ValueError(f"{key} 必须为 true 或 false")
        for key in ("mail_daily_limit", "mail_batch_limit", "mail_min_interval_seconds", "search_min_interval_seconds", "mail_external_usage_estimate"):
            if key in patch:
                val = float(patch[key])
                if val < 0 or val > 1_000_000 or (key not in {"mail_external_usage_estimate"} and val < 1):
                    raise ValueError(f"{key} 数值不合理")
                patch[key] = val if key.endswith("seconds") else int(val)
        if "public_url" in patch and patch["public_url"]:
            parsed = urlparse(str(patch["public_url"]))
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
                raise ValueError("公开入口须为不包含密码、查询或片段的 HTTPS 地址")
            patch["public_url"] = patch["public_url"].rstrip("/")
        if patch.get("mail_policy_reviewed"):
            patch["mail_policy_reviewed_at"] = now()
        result = store.update_settings(patch)
        store.event("settings_changed", {"keys": list(patch)})
        return result

    @app.post("/api/demo/load", dependencies=auth, summary="载入明确标注的演示资料，不发送真实邮件")
    def demo_load():
        if not store.settings().get("demo_mode"):
            raise ValueError("请先开启演示模式，再载入演示资料")
        path = ROOT / "demo" / "data.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        source = data.get("entities", data)
        counts = {}
        for kind, records in source.items():
            if kind not in READABLE or not isinstance(records, list):
                continue
            for record in records:
                record = {**record, "demo": True}
                record_id = str(record.get("id") or f"demo-{uuid.uuid4().hex[:12]}")
                if not record_id.startswith("demo"):
                    record_id = f"demo-{record_id}"
                if kind == "market_records":
                    market.import_records([{**record, "id": record_id}])
                else:
                    store.put(kind, record, record_id)
            counts[kind] = len(records)
        store.event("demo_loaded", {"counts": counts})
        return {"demo": True, "counts": counts, "note": "虚构资料；没有真实获客或发送邮件"}

    @app.post("/api/import", dependencies=auth, summary="在本机导入客户、产品和补充附件")
    async def import_file(file: UploadFile = File(...), kind: str | None = None):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".xlsx", ".csv", ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp", ".txt"}:
            raise ValueError("支持 XLSX、CSV、PDF、DOCX、图片和文本文件")
        upload_dir = config.data_dir / "uploads"
        upload_dir.mkdir(exist_ok=True)
        path = upload_dir / f"{uuid.uuid4().hex}{suffix}"
        total = 0
        try:
            with path.open("wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > 30 * 1024 * 1024:
                        raise ValueError("文件超过 30 MB，请拆分后导入")
                    handle.write(chunk)
            result = market.import_file(path) if kind == "market_records" else imports.import_file(path, kind)
            if isinstance(result, dict):
                result["uploaded_file"] = register_file(path)
            return outputs(result)
        except Exception:
            # Successful imports retain original files. Failed imports cannot leak disk indefinitely.
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.get("/api/export/{kind}", dependencies=auth, summary="导出业务记录为 CSV")
    def export(kind: str):
        if kind not in READABLE - {"files"}:
            raise ValueError("不支持的导出类型")
        records = store.list(kind, 50000)
        fields = sorted({key for record in records for key in record})
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {}
            for key, value in record.items():
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    value = "'" + value
                row[key] = value
            writer.writerow(row)
        return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'})

    @app.post("/api/import/from-file", dependencies=auth, summary="解析已经上传或从邮箱取得的业务文件，提取内容等待核对")
    def import_existing(request: dict[str, Any] = Body(...)):
        file = store.get("files", str(request.get("file_id", "")))
        path = safe_path(file["path"])
        kind = request.get("kind")
        result = market.import_file(path) if kind == "market_records" else imports.import_file(path, kind)
        return outputs(result)

    @app.post("/api/backup", dependencies=auth, summary="生成本机业务备份，默认不包含认证密钥")
    def backup():
        directory = config.data_dir / "backups"
        directory.mkdir(exist_ok=True)
        target = directory / f"trade-backup-{uuid.uuid4().hex[:12]}.zip"
        with tempfile.TemporaryDirectory(dir=directory) as tmp:
            snapshot = Path(tmp) / "trade.sqlite3"
            store.backup_database(snapshot)
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps({"version": 1, "original_data_dir": str(config.data_dir.resolve()), "created_at": now()}, ensure_ascii=False))
                archive.write(snapshot, "trade.sqlite3")
                for folder in ("uploads", "documents", "imports", "mail_attachments", "mail_inbound"):
                    root = config.data_dir / folder
                    if root.exists():
                        for file in root.rglob("*"):
                            if file.is_file() and not file.is_symlink():
                                archive.write(file, file.relative_to(config.data_dir).as_posix())
        store.event("backup_created", {"name": target.name})
        return {"files": [register_file(target)], "includes_credentials": False}

    @app.get("/api/files/{file_id}", dependencies=auth, summary="下载已登记的业务文件")
    def download(file_id: str):
        record = store.get("files", file_id)
        return FileResponse(safe_path(record["path"]), filename=record["name"])

    @app.get("/api/template", dependencies=auth, include_in_schema=False)
    def template(name: str = "trade"):
        filename = "market-data-template.xlsx" if name == "market" else "trade-data-template.xlsx"
        return FileResponse(ROOT / "templates" / filename, filename=filename)

    @app.get("/api/tasks/{task_id}", dependencies=auth, summary="查询任务进度与结果；不要重复提交同一发送任务")
    def task_get(task_id: str):
        return outputs(store.get("tasks", task_id))

    @app.post("/api/acquisition/search", dependencies=auth, summary="在已选国家寻找大小企业和小商户，保存全部已发现合格线索")
    def search(request: SearchRequest):
        return tasks.submit("acquisition", acquisition.search, dump(request))

    @app.post("/api/acquisition/enrich", dependencies=auth, summary="访问客户公开官网补充有来源的业务事实与联系方式")
    def enrich(request: CustomerRequest):
        return tasks.submit("enrichment", acquisition.enrich, request.customer_id)

    @app.post("/api/markets/import", dependencies=auth, summary="导入官方汇总贸易统计")
    def market_import(request: RecordsRequest):
        return market.import_records(request.records)

    @app.post("/api/markets/analyze", dependencies=auth, summary="分析官方统计的国家机会，不将统计单位值当作产品报价")
    def analyze(request: MarketRequest):
        return tasks.submit("market_analysis", market.analyze, dump(request))

    @app.post("/api/markets/select", dependencies=auth, summary="按用户选择确定目标国家")
    def select(request: SelectRequest):
        return market.select(request.country)

    @app.get("/api/mail/status", dependencies=auth, summary="读取邮箱授权、演示模式及发送配置状态")
    def mail_status():
        return mail.status()

    @app.post("/api/mail/oauth/start", dependencies=auth, include_in_schema=False)
    def oauth_start():
        return mail.oauth_start()

    @app.post("/api/mail/oauth/complete", dependencies=auth, include_in_schema=False)
    def oauth_complete(request: CompleteOAuth):
        return mail.oauth_complete(request.code, request.state)

    @app.get("/api/mail/oauth/callback", include_in_schema=False)
    def oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        require_local(request)
        if error or not code or not state:
            return HTMLResponse("授权未完成，请返回工作台重新授权。", status_code=400)
        mail.oauth_complete(code, state)
        return HTMLResponse("邮箱授权已完成。请关闭此页，返回本机工作台。")

    @app.post("/api/mail/sync", dependencies=auth, summary="按用户指令读取企业邮箱，整理外贸邮件与新客户询盘")
    def mail_sync(request: SyncRequest):
        return tasks.submit("mail_sync", mail.sync, dump(request))

    @app.post("/api/mail/drafts", dependencies=auth, summary="保存 AI 按该客户事实单独定制的待审邮件")
    def draft(request: DraftRequest):
        data = dump(request)
        for attachment in data.get("attachments", []):
            if attachment.get("file_id"):
                attachment["path"] = str(safe_path(store.get("files", attachment["file_id"])["path"]))
            elif attachment.get("path"):
                attachment["path"] = str(safe_path(attachment["path"]))
        return mail.create_draft(data)

    @app.post("/api/mail/approve", dependencies=auth, summary="用户核对完整内容后批准选定草稿的具体版本")
    def approve(request: ApprovalRequest):
        return mail.approve_batch(dump(request))

    @app.post("/api/mail/batches/{batch_id}/send", dependencies=auth, summary="发送已批准的批次；按间隔和限额执行，演示只模拟")
    def send(batch_id: str):
        return tasks.submit("mail_send", mail.run_batch, batch_id)

    @app.post("/api/mail/batches/{batch_id}/pause", dependencies=auth, summary="暂停当前邮件批次")
    def pause(batch_id: str):
        return mail.pause_batch(batch_id)

    @app.post("/api/mail/batches/{batch_id}/resolve", dependencies=auth, summary="用户核对发送记录后解决结果不明状态，避免盲目重发")
    def resolve_delivery(batch_id: str, request: dict[str, Any] = Body(...)):
        return mail.resolve_delivery({**request, "batch_id": batch_id})

    @app.post("/api/whatsapp", dependencies=auth, summary="生成 WhatsApp 个性化消息和聊天链接，由用户手动发送")
    def whatsapp(request: WhatsAppRequest):
        return mail.whatsapp(dump(request))

    @app.post("/api/whatsapp/{message_id}/status", dependencies=auth, summary="按用户报告记录 WhatsApp 手动发送或回复，不视为平台送达验证")
    def whatsapp_status(message_id: str, request: dict[str, Any] = Body(...)):
        return mail.record_whatsapp({**request, "id": message_id})

    @app.post("/api/profit-rules", dependencies=auth, summary="提出有依据的利润规则，等待用户确认")
    def profit_rule(request: ProfitRequest):
        return business.create_profit_rule(dump(request))

    @app.post("/api/profit-rules/{rule_id}/confirm", dependencies=auth, summary="由用户确认该版本的利润底线及目标")
    def confirm_profit(rule_id: str):
        return business.confirm_profit_rule(rule_id)

    @app.post("/api/quotes", dependencies=auth, summary="按真实规格、成本、数量和确认利润规则计算报价与谈判区间")
    def quote(request: QuoteRequest):
        return business.quote(dump(request))

    @app.post("/api/orders", dependencies=auth, summary="建立订单与合同草稿记录，不自动签约或收付款")
    def order(request: OrderRequest):
        return business.create_order(dump(request))

    @app.post("/api/order-updates", dependencies=auth, summary="将手动或邮件提取的生产、物流、收款及售后信息提交待核对")
    def update(request: UpdateRequest):
        return business.propose_update(dump(request))

    @app.post("/api/order-updates/{update_id}/confirm", dependencies=auth, summary="用户核对后更新订单进度；付款声明不自动代表已到账")
    def confirm_update(update_id: str):
        return business.confirm_update(update_id)

    @app.post("/api/orders/{order_id}/documents", dependencies=auth, summary="生成订单合同及发票、装箱单草稿文件")
    def documents(order_id: str):
        return outputs(business.generate_documents(order_id))

    @app.post("/api/documents/verify", dependencies=auth, summary="确定性核验发票与装箱单字段和计算一致性")
    def verify(request: dict[str, Any] = Body(...)):
        for key in ("invoice_path", "packing_list_path"):
            if request.get(key):
                request[key] = str(safe_path(request[key]))
        return business.verify_documents(request)

    @app.post("/api/followups", dependencies=auth, summary="生成客户跟进、售后和复购待办；不自主发送")
    def followups(request: FollowupRequest):
        return business.followups(dump(request))

    @app.get("/openapi-actions.json", include_in_schema=False)
    def actions_schema():
        schema = copy.deepcopy(app.openapi())
        # Keep Actions concise. Installation, binary uploads and policy configuration stay local.
        excluded = {"/api/import", "/api/import/from-file", "/api/export/{kind}", "/api/backup", "/api/files/{file_id}", "/api/demo/load", "/api/markets/import", "/api/mail/batches/{batch_id}/resolve"}
        for path in list(schema["paths"]):
            if path in excluded:
                schema["paths"].pop(path)
                continue
            for method in list(schema["paths"][path]):
                if path == "/api/settings" and method != "get":
                    schema["paths"][path].pop(method)
                    continue
                operation = schema["paths"][path][method]
                if isinstance(operation, dict):
                    operation["x-openai-isConsequential"] = method not in {"get", "head"}
                    operation["security"] = [{"HTTPBearer": []}]
        public_url = store.settings().get("public_url")
        schema["servers"] = [{"url": public_url or f"http://127.0.0.1:{config.port}", "description": "请先在本机连接向导配置实际 HTTPS 入口"}]
        schema["info"]["description"] = "用户指令触发的外贸工作台。真实发送须批准具体草稿版本；演示不作为真实接通证据。"
        return schema

    return app
