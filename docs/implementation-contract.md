# Implementation contract (internal)

Package `trade_agent`; FastAPI app; local SQLite JSON records; no paid model API. ChatGPT supplies analysis/drafts through authenticated Actions. Local HTML UI uses the same authenticated API. Real integrations and demo data are separate.

Root-owned files: `trade_agent/app.py`, `store.py`, `config.py`, `tasks.py`, `__init__.py`, `__main__.py`, requirements, core tests, bundle.

Shared `Store(data_dir)` interface: `.put(kind, data, record_id=None) -> dict` (sets id/created_at/updated_at), `.get(kind,id) -> dict` (KeyError if absent), `.list(kind,limit=5000) -> list[dict]`, `.delete(kind,id)`, `.settings() -> dict`, `.update_settings(patch) -> dict`, `.event(action,details)`, `.lock` (RLock), `.data_dir` (Path). Kind names are plural. All data is JSON serializable. Importers may upsert existing id with put. Never persist secrets in general records or API results.

Config owns data_dir, API key, server URL, Gmail credential/token paths. Use store.settings() for business preferences, not secrets. All integration methods take Store or data_dir rather than globals.

TaskManager(store).submit(kind, func, *args, **kwargs) starts a task immediately in a small thread pool, returns persisted task with id/state. Callable returns JSON-serializable result. Workers update result/error; no autonomous scheduled tasks.

Modules owned by delegates:
- `trade_agent/acquisition.py`, `market.py`: leads search/enrichment & official statistics. `AcquisitionService(store).search(request:dict)->dict`, `.enrich(customer_id)->dict`; `MarketService(store).import_records(records:list)->dict`, `.analyze(request:dict)->dict`, `.select(country:str)->dict`. Save customers, market_records, market_selections. Demo search explicitly marked and never runs as real. No lead discarded solely because of size.
- `trade_agent/mail.py`: `MailService(store,data_dir).status()`, `.oauth_start()`, `.oauth_complete(code,state)`, `.sync(request)`, `.create_draft(request)`, `.approve_batch(request)`, `.run_batch(batch_id)`, `.pause_batch(batch_id)`, `.whatsapp(request)`. Save mail_drafts/mail_batches/email_messages/inquiries. Real sends require exact-version approval and reviewed policy; demo sends only record simulations. Gmail OAuth tokens kept outside records. Full inbox read on user command. No unsupported automatic personalized claims.
- `trade_agent/business.py`, `imports.py`: `BusinessService(store).create_profit_rule(request)`, `.confirm_profit_rule(id)`, `.quote(request)`, `.create_order(request)`, `.propose_update(request)`, `.confirm_update(id)`, `.generate_documents(order_id)`, `.verify_documents(request)`, `.followups(request)`; `ImportService(store).import_file(path,kind=None)->dict`. Save products, profit_rules, quotes, orders, order_updates. Draft documents never execute signatures/payments. Quote amounts use Decimal and true gross margin; incomplete costs flagged.
- `static/index.html`: local dashboard, authenticated requests, installation status, demo load, data, acquisition, market, quote/profit, drafts/approval/batches, WhatsApp, order progress/review/documents/followup, tasks/settings. Fetch route contract below. No frontend framework or CDN.
- `scripts/*`, `docs/QUICKSTART.zh-CN.md`, `docs/GPT-INSTRUCTIONS.zh-CN.md`, `demo/*`: Windows installers/start/stop/tunnel, portable instructions, demo data.

Root REST endpoints (JSON unless upload):
GET /health (public, minimal), /api/status, /api/entities/{kind}, /api/entities/{kind}/{id}; POST /api/entities/{kind} (limited manual kinds); GET /api/settings; PATCH /api/settings; POST /api/demo/load; POST /api/import (multipart file, optional kind); GET /api/export/{kind}; POST /api/backup.
GET /api/tasks/{id}; POST /api/acquisition/search and /api/acquisition/enrich (task); POST /api/markets/import, /api/markets/analyze, /api/markets/select.
GET /api/mail/status; POST /api/mail/oauth/start, /api/mail/oauth/complete, /api/mail/sync (task), /api/mail/drafts, /api/mail/approve, /api/mail/batches/{id}/send (task), /api/mail/batches/{id}/pause; POST /api/whatsapp.
POST /api/profit-rules; POST /api/profit-rules/{id}/confirm; POST /api/quotes; POST /api/orders; POST /api/order-updates; POST /api/order-updates/{id}/confirm; POST /api/orders/{id}/documents; POST /api/documents/verify; POST /api/followups.
GET /api/files/{file_id} authenticated; root registers generated file paths and serves only safe data_dir children. Module outputs include absolute `files` paths, root converts to downloadable file ids.
GET /openapi-actions.json public schema only; all Actions operations Bearer API key. Canonical public URL supplied locally. Mutation operations x-openai-isConsequential true. CORS not wildcard; UI local same origin, no API key in URLs or public assets. Local admin setup only loopback + loopback Host (no tunnel access) can obtain API key. All /api routes require Bearer.

Default settings must be configurable: demo_mode true initially; daily caps/min_interval conservative but not called official limits; send policy review false initially; no real sending until account configured and rules reviewed. A demo entity is never silently real. Settings changes use the authenticated local UI; settings mutations are excluded from the Actions schema.

Do not edit another delegate's files. Report final public method signature changes to root; add substantive tests only for high-impact calculations, approval/rate controls, data state and auth boundaries.
