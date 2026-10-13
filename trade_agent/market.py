"""Official aggregate trade data, explicitly distinct from company leads/prices.

The free Comtrade adapter uses the documented public preview. Preview responses
can be truncated and must not be described as a complete market measurement.
Other official providers are supported by importing their exports.
"""
from __future__ import annotations

import hashlib
import math
import csv
import io
import re
import shutil
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

import httpx


COUNTRIES = {
    "US": ("United States", "美国", 842), "GB": ("United Kingdom", "英国", 826),
    "DE": ("Germany", "德国", 276), "FR": ("France", "法国", 250),
    "IT": ("Italy", "意大利", 380), "ES": ("Spain", "西班牙", 724),
    "NL": ("Netherlands", "荷兰", 528), "BE": ("Belgium", "比利时", 56),
    "CA": ("Canada", "加拿大", 124), "AU": ("Australia", "澳大利亚", 36),
    "NZ": ("New Zealand", "新西兰", 554), "JP": ("Japan", "日本", 392),
    "KR": ("South Korea", "韩国", 410), "CN": ("China", "中国", 156),
    "IN": ("India", "印度", 699), "SG": ("Singapore", "新加坡", 702),
    "MY": ("Malaysia", "马来西亚", 458), "TH": ("Thailand", "泰国", 764),
    "VN": ("Vietnam", "越南", 704), "ID": ("Indonesia", "印度尼西亚", 360),
    "PH": ("Philippines", "菲律宾", 608), "AE": ("United Arab Emirates", "阿联酋", 784),
    "SA": ("Saudi Arabia", "沙特阿拉伯", 682), "ZA": ("South Africa", "南非", 710),
    "KE": ("Kenya", "肯尼亚", 404), "EG": ("Egypt", "埃及", 818),
    "BR": ("Brazil", "巴西", 76), "MX": ("Mexico", "墨西哥", 484),
    "PL": ("Poland", "波兰", 616), "TR": ("Türkiye", "土耳其", 792),
    "RU": ("Russia", "俄罗斯", 643), "SE": ("Sweden", "瑞典", 752),
    "NO": ("Norway", "挪威", 578), "DK": ("Denmark", "丹麦", 208),
    "CH": ("Switzerland", "瑞士", 756), "AT": ("Austria", "奥地利", 40),
    "IE": ("Ireland", "爱尔兰", 372), "PT": ("Portugal", "葡萄牙", 620),
    "HK": ("Hong Kong", "中国香港", 344), "TW": ("Taiwan", "中国台湾", 490),
    "BD": ("Bangladesh", "孟加拉国", 50), "PK": ("Pakistan", "巴基斯坦", 586),
}
_ALIASES = {"usa": "US", "u.s.": "US", "uk": "GB", "south korea": "KR",
            "korea, rep.": "KR", "republic of korea": "KR", "turkey": "TR",
            "viet nam": "VN", "russian federation": "RU", "hong kong": "HK"}
for _code, (_english, _chinese, _un_code) in COUNTRIES.items():
    for _alias in (_code, _english, _chinese, str(_un_code)):
        _ALIASES[_alias.casefold()] = _code


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_country(value: Any) -> tuple[str, str | None]:
    name = str(value or "").strip()
    if not name:
        raise ValueError("请提供国家名称或 ISO 两位国家代码。")
    code = _ALIASES.get(name.casefold())
    return (COUNTRIES[code][0], code) if code else (name, None)


def _first(row: dict, *keys: str, default=None):
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return default


def _number(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"{field} 必须为数字，不能将缺失数据填成零。") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} 必须为非负有限数字。")
    numeric = float(result)
    if not math.isfinite(numeric):
        raise ValueError(f"{field} 数值超出可处理范围。")
    return numeric


def _boolean(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.strip().casefold()
    if value in (True, 1, "true", "yes", "y", "是"):
        return True
    if value in (False, 0, "false", "no", "n", "否"):
        return False
    raise ValueError("complete_period 必须为布尔值，不能猜测统计期是否完整。")


def normalize_record(row: dict) -> dict:
    """Normalize explicit fields; do not infer amounts, unit, HS version or coverage."""
    aliases = {"报告国家": "reporter", "报告国名称": "reporter", "伙伴国": "partner", "伙伴国名称": "partner",
               "流向": "flow", "年份": "period", "年月": "period", "商品代码": "hs_code", "HS编码": "hs_code",
               "hs编码": "hs_code", "分类版本": "hs_version", "金额美元": "value_usd", "美元金额": "value_usd",
               "贸易金额": "value", "计量单位": "quantity_unit", "净重公斤": "net_weight_kg", "净重(kg)": "net_weight_kg",
               "采集日期": "collected_at", "数据覆盖": "coverage"}
    row = dict(row)
    for key, value in list(row.items()):
        normalized_key = str(key).strip()
        canonical = aliases.get(normalized_key)
        if canonical:
            row.setdefault(canonical, value)
        row.setdefault(normalized_key, value)
        row.setdefault(normalized_key.lower().replace(" ", "_"), value)
    reporter = _first(row, "reporter", "reporterDesc", "reporter_country", "报告国")
    if not reporter:
        raise ValueError("市场统计缺少报告国 reporter。")
    reporter, reporter_code = canonical_country(reporter)
    partner_raw = str(_first(row, "partner", "partnerDesc", "partner_country", "贸易伙伴", default="")).strip()
    if partner_raw.casefold() in ("world", "all", "0", "世界", "全球", "全部"):
        partner, partner_code = "World", "WORLD"
    elif partner_raw:
        partner, partner_code = canonical_country(partner_raw)
    else:
        partner, partner_code = None, None
    flow_raw = str(_first(row, "flow", "flowCode", "flowDesc", "贸易流向", default="")).strip().casefold()
    flow = {"m": "import", "imports": "import", "import": "import", "进口": "import",
            "x": "export", "exports": "export", "export": "export", "出口": "export"}.get(flow_raw)
    if not flow:
        raise ValueError("贸易流向必须明确为 import/进口 或 export/出口。")
    period = str(_first(row, "period", "year", "时期", default="")).strip()
    if not period.isdigit() or len(period) not in (4, 6):
        raise ValueError("period 应为 YYYY 或 YYYYMM。")
    year = int(period[:4])
    if year < 1962 or year > datetime.now(timezone.utc).year + 1:
        raise ValueError("统计年份不在可接受范围。")
    if len(period) == 6 and not 1 <= int(period[4:]) <= 12:
        raise ValueError("统计月份无效。")
    hs_code = str(_first(row, "hs_code", "cmdCode", "商品编码", default="")).strip()
    if hs_code.endswith(".0") and hs_code[:-2].isdigit():
        hs_code = hs_code[:-2]
    if not hs_code.isdigit() or len(hs_code) not in (2, 4, 6, 8, 10):
        raise ValueError("hs_code 需为 2/4/6/8/10 位文本编码，保留前导零。")
    currency = str(_first(row, "currency", "币种", default="")).strip().upper()
    value = _number(_first(row, "value", "value_usd", "primaryValue", "tradeValue", "金额"), "value")
    if _first(row, "value_usd") is not None or _first(row, "primaryValue", "tradeValue") is not None:
        currency = currency or "USD"
    if not currency and value is not None:
        raise ValueError("金额非空时必须提供 currency/币种，不能猜测美元。")
    value_multiplier = _number(_first(row, "value_multiplier", "金额倍率", default=1), "value_multiplier")
    if not value_multiplier:
        raise ValueError("value_multiplier 必须大于零。")
    value = value * value_multiplier if value is not None else None
    quantity = _number(_first(row, "quantity", "qty", "数量"), "quantity")
    net_weight = _number(_first(row, "net_weight_kg", "netWgt", "净重kg"), "net_weight_kg")
    unit = str(_first(row, "quantity_unit", "qtyUnitAbbr", "数量单位", default="")).strip() or None
    source = str(_first(row, "source", "来源", default="user_import")).strip()
    result = {
        "reporter": reporter, "reporter_code": reporter_code, "partner": partner,
        "partner_code": partner_code, "flow": flow, "period": period,
        "frequency": "annual" if len(period) == 4 else "monthly", "hs_code": hs_code,
        "hs_version": str(_first(row, "hs_version", "classificationCode", "HS版本", default="unknown")),
        "value": value, "currency": currency or None, "value_multiplier": 1,
        "quantity": quantity, "quantity_unit": unit, "net_weight_kg": net_weight,
        "source": source, "source_url": _first(row, "source_url", "来源链接"),
        "collected_at": _first(row, "collected_at", "采集时间", default=utcnow()),
        "published_at": _first(row, "published_at", "发布日期"),
        "complete_period": _boolean(_first(row, "complete_period", "完整统计期")),
        "coverage": str(_first(row, "coverage", default="unverified")),
        "valuation_basis": _first(row, "valuation_basis", "计价基础"),
        "demo": _boolean(row.get("demo", False)) or False,
        "source_file": row.get("source_file"), "source_row": row.get("source_row"),
        "source_sheet": row.get("source_sheet"),
        "is_quantity_estimated": _boolean(row.get("isQtyEstimated")),
        "is_weight_estimated": _boolean(row.get("isNetWgtEstimated")),
    }
    result["unit_value"] = value / quantity if value is not None and quantity and unit else None
    result["unit_value_basis"] = f"{currency}/{unit}" if result["unit_value"] is not None else None
    result["weight_unit_value"] = value / net_weight if value is not None and net_weight else None
    result["unit_value_warning"] = "汇总统计单位价值，不能代替同规格 SKU 报价。"
    # Exact identity avoids duplicate uploads, while dissimilar sources never get summed.
    identity = [result[k] for k in ("reporter", "partner", "flow", "period", "hs_code",
                                   "hs_version", "source", "currency", "demo")]
    result["record_key"] = hashlib.sha256(repr(identity).encode()).hexdigest()
    return result


class MarketService:
    def __init__(self, store):
        self.store = store

    def import_records(self, records: list) -> dict:
        if not isinstance(records, list) or len(records) > 50000:
            raise ValueError("统计导入必须为列表，单次最多 50000 条。")
        accepted, errors = [], []
        existing = {r.get("record_key"): r for r in self.store.list("market_records", limit=100000)}
        for index, row in enumerate(records):
            try:
                if not isinstance(row, dict):
                    raise ValueError("每条统计必须为对象。")
                data = normalize_record(row)
                prior = existing.get(data["record_key"])
                saved = self.store.put("market_records", data, prior["id"] if prior else None)
                existing[data["record_key"]] = saved
                accepted.append(saved)
            except (ValueError, TypeError) as exc:
                errors.append({"row": index + 1, "error": str(exc)})
        self.store.event("market_import", {"accepted": len(accepted), "rejected": len(errors)})
        return {"status": "partial" if errors and accepted else "error" if errors else "ok",
                "accepted": len(accepted), "rejected": len(errors), "records": accepted,
                "errors": errors, "warning": "导入保留原始口径；不同来源、HS 版本、金额币种不会直接相加。"}

    def import_file(self, path) -> dict:
        """Read canonical XLSX/CSV exports; formulas never execute or become values."""
        source = Path(path).resolve()
        if not source.is_file() or source.suffix.lower() not in (".xlsx", ".csv"):
            raise ValueError("官方统计导入支持 XLSX/CSV；请按统计模板整理明确的口径与单位。")
        if source.stat().st_size > 25 * 1024 * 1024:
            raise ValueError("统计文件不得超过 25MB。")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        import_id = "market-" + uuid.uuid4().hex[:16]
        folder = Path(self.store.data_dir) / "imports" / import_id
        folder.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w.\-]", "_", source.name)[:120]
        original = folder / safe_name
        shutil.copyfile(source, original)
        records, read_errors = [], []

        def append_row(headers, values, row_number, sheet, formulas=()):
            if not any(value is not None and value != "" for value in values):
                return
            if formulas:
                read_errors.append({"row": row_number, "sheet": sheet, "error": "含公式的行未导入；请先核对并粘贴为值。"})
                return
            if len(records) >= 50000:
                raise ValueError("统计文件单次最多 50000 条。")
            row = dict(zip(headers, values))
            # Import is real statistical data. A spreadsheet cannot toggle demo modes.
            row.update(demo=False, source_file=digest, source_row=row_number, source_sheet=sheet)
            records.append(row)

        if source.suffix.lower() == ".csv":
            raw = original.read_bytes()
            text = None
            for encoding in ("utf-8-sig", "gb18030", "utf-16"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    pass
            if text is None:
                raise ValueError("CSV 编码无法识别，请另存为 UTF-8。")
            try:
                dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(io.StringIO(text), dialect=dialect)
            headers = [h.strip().lstrip("\ufeff") for h in next(reader, [])]
            if not headers or len(headers) != len(set(headers)):
                raise ValueError("统计表需第一行为不重复字段名。")
            for row_number, values in enumerate(reader, 2):
                formulas = [v for v in values if v.lstrip().startswith("=")]
                append_row(headers, values, row_number, "CSV", formulas)
        else:
            from openpyxl import load_workbook
            try:
                with ZipFile(original) as archive:
                    entries = archive.infolist()
                    if len(entries) > 10000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
                        raise ValueError("解压后的统计表超过读取上限。")
            except BadZipFile as exc:
                raise ValueError("文件不是有效 XLSX。") from exc
            workbook = load_workbook(original, read_only=True, data_only=False)
            try:
                for sheet in workbook:
                    if sheet.title.casefold() in ("说明", "填写说明", "readme", "instructions", "metadata", "summary"):
                        continue
                    iterator = iter(sheet.iter_rows())
                    headers = [str(c.value or "").strip() for c in next(iterator, [])]
                    if not headers or len(headers) != len(set(headers)):
                        read_errors.append({"sheet": sheet.title, "error": "字段名空缺或重复；此表未导入。"})
                        continue
                    for row_number, cells in enumerate(iterator, 2):
                        append_row(headers, [c.value for c in cells], row_number, sheet.title,
                                   [c for c in cells if c.data_type == "f"])
            finally:
                workbook.close()
        result = self.import_records(records)
        result["errors"] = read_errors + result["errors"]
        result["rejected"] += len(read_errors)
        if result["errors"]:
            result["status"] = "partial" if result["accepted"] else "error"
        result.update(import_id=import_id, sha256=digest, file_name=source.name, files=[str(original.resolve())],
                      formulas_executed=False)
        self.store.put("imports", {"import_id": import_id, "kind": "market_records", "file_name": source.name,
                                  "sha256": digest, "accepted": result["accepted"], "rejected": result["rejected"],
                                  "status": result["status"], "original_path": str(original.resolve())}, import_id)
        return result

    def select(self, country: str) -> dict:
        name, code = canonical_country(country)
        selection = self.store.put("market_selections", {"country": name, "country_code": code,
                                  "confirmed": True, "selected_at": utcnow()})
        self.store.update_settings({"selected_country": name, "selected_country_code": code})
        self.store.event("market_select", {"country": name, "country_code": code})
        return selection

    def fetch_comtrade(self, request: dict) -> dict:
        """Finite, no-key public preview; errors remain errors, never synthetic zeros."""
        hs_codes = request.get("hs_codes") or [request.get("hs_code", "")]
        if isinstance(hs_codes, str):
            hs_codes = [hs_codes]
        hs_codes = [str(x).strip() for x in hs_codes]
        if not hs_codes or len(hs_codes) > 5 or any(not c.isdigit() or len(c) not in (2, 4, 6) for c in hs_codes):
            raise ValueError("Comtrade 单次预览最多 5 个 2/4/6 位 HS 编码。")
        year = str(request.get("year", datetime.now(timezone.utc).year - 2))
        if not year.isdigit() or len(year) != 4:
            raise ValueError("Comtrade year 必须为四位年份。")
        reporters = request.get("reporters") or request.get("countries") or []
        if isinstance(reporters, str):
            reporters = [reporters]
        if not reporters or len(reporters) > 10:
            raise ValueError("免费预览请明确提供 1 至 10 个候选 countries/reporters。")
        normalized = []
        for value in reporters:
            name, code = canonical_country(value)
            if code:
                normalized.append((name, COUNTRIES[code][2]))
            elif str(value).isdigit():
                normalized.append((str(value), int(value)))
            else:
                raise ValueError(f"未知 Comtrade 报告国代码：{value}；请提供 UN 数字代码。")
        url = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
        records, source_results = [], []
        # Only named public endpoint; do not accept an arbitrary endpoint from AI/user input.
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            for name, code in normalized:
                params = {"period": year, "reporterCode": code, "cmdCode": ",".join(hs_codes),
                          "flowCode": "M", "partnerCode": 0, "partner2Code": 0,
                          "customsCode": "C00", "motCode": 0, "maxRecords": 500}
                try:
                    response = client.get(url, params=params)
                    if response.status_code in (401, 403, 429):
                        source_results.append({"country": name, "status": "access_or_quota_limited",
                                               "http_status": response.status_code,
                                               "action": "稍后手动重试或从官方页面导出后导入；不绕过限制。"})
                        if response.status_code == 429:
                            break
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    rows = payload.get("data")
                    if not isinstance(rows, list):
                        raise ValueError("官方响应未包含 data 列表。")
                    count = 0
                    row_errors = []
                    for row in rows:
                        try:
                            prepared = dict(row, source="UN Comtrade public preview", source_url=str(response.url),
                                            currency="USD", coverage="preview_possibly_truncated",
                                            complete_period=None, demo=False)
                            prepared.setdefault("reporter", row.get("reporterDesc") or name)
                            prepared.setdefault("partner", row.get("partnerDesc") or "World")
                            prepared.setdefault("hs_version", row.get("classificationCode") or "HS-unspecified")
                            records.append(normalize_record(prepared))
                            count += 1
                        except (ValueError, TypeError) as exc:
                            row_errors.append(str(exc))
                    source_results.append({"country": name, "status": "preview" if count else "no_data",
                                           "records": count, "row_errors": row_errors[:10],
                                           "coverage": "preview_possibly_truncated", "url": str(response.url)})
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    source_results.append({"country": name, "status": "fetch_failed", "error": str(exc)[:400],
                                           "action": "检查网络/官方服务状态，或导入官方导出数据。"})
        imported = self.import_records(records) if records else None
        return {"status": "preview" if records else "unconnected", "records": len(records),
                "sources": source_results, "import_result": imported,
                "warning": "免费预览不保证完整，不能据此宣称已得到国家全部贸易量。"}

    def analyze(self, request: dict) -> dict:
        source = request.get("source", "imported")
        live = self.fetch_comtrade(request) if source == "comtrade" else None
        if source not in ("imported", "comtrade", "demo"):
            return {"status": "import_required", "source": source, "candidates": [],
                    "action": "该来源自动接口尚未接通，请先导入官方 CSV/XLSX 导出。"}
        demo = source == "demo"
        if demo and not self.store.settings().get("demo_mode", True):
            raise ValueError("演示模式已关闭，不能将演示数据用于真实市场分析。")
        rows = [r for r in self.store.list("market_records", limit=100000) if bool(r.get("demo")) == demo]
        hs_filter = request.get("hs_codes") or ([request["hs_code"]] if request.get("hs_code") else [])
        if isinstance(hs_filter, str):
            hs_filter = [hs_filter]
        # Prefix filtering is allowed, but parent+child rows are never aggregated together.
        if hs_filter:
            rows = [r for r in rows if any(str(r.get("hs_code", "")).startswith(str(h)) for h in hs_filter)]
        if request.get("countries"):
            countries = request["countries"]
            if isinstance(countries, str):
                countries = [countries]
            names = {canonical_country(c)[0] for c in countries}
            rows = [r for r in rows if r.get("reporter") in names or r.get("partner") in names]
        # Exact series only: adding World totals, China bilateral and source mirrors would double-count.
        groups = defaultdict(list)
        for row in rows:
            if row.get("flow") == "import" and row.get("partner_code") == "WORLD":
                country, scope = row.get("reporter"), "world_import"
            elif row.get("flow") == "export" and row.get("reporter_code") == "CN" and row.get("partner"):
                country, scope = row["partner"], "china_export_to_market"
                if row.get("partner_code") == "WORLD":
                    continue
            else:
                continue
            key = (country, scope, row.get("hs_code"), row.get("hs_version"), row.get("source"),
                   row.get("currency"), row.get("frequency"), row.get("valuation_basis"))
            groups[key].append(row)
        candidates = []
        for key, series in groups.items():
            country, scope, hs, version, provider, currency, frequency, valuation = key
            series.sort(key=lambda x: x["period"])
            latest = series[-1]
            eligible = [r for r in series if r.get("complete_period") is True and r.get("value") is not None]
            growth, growth_periods = None, None
            if len(eligible) >= 2:
                newest = eligible[-1]
                previous = next((r for r in reversed(eligible[:-1])
                                 if (frequency == "annual" and int(r["period"]) == int(newest["period"]) - 1)
                                 or (frequency == "monthly" and int(r["period"]) == int(newest["period"]) - 100)), None)
                if previous and previous["value"] > 0:
                    growth = round((newest["value"] / previous["value"] - 1) * 100, 4)
                    growth_periods = [previous["period"], newest["period"]]
            missing = ["关税及准入", "物流成本", "产品适配", "客户可触达性"]
            if latest.get("complete_period") is not True:
                missing.append("统计期完整性未核验")
            if latest.get("coverage") not in ("complete", "official_complete"):
                missing.append("数据覆盖范围未核验")
            if growth is None:
                missing.append("缺少连续可比完整期间，未计算同比")
            candidates.append({"country": country, "scope": scope, "hs_code": hs, "hs_version": version,
                               "source": provider, "currency": currency, "frequency": frequency,
                               "latest_period": latest["period"], "latest_value": latest.get("value"),
                               "growth_percent": growth, "growth_periods": growth_periods,
                               "valuation_basis": valuation, "coverage": latest.get("coverage"),
                               "unit_value": latest.get("unit_value"),
                               "unit_value_basis": latest.get("unit_value_basis"),
                               "weight_unit_value": latest.get("weight_unit_value"),
                               "record_ids": [r["id"] for r in series], "missing": missing, "demo": demo,
                               "selection_required": True, "recommendation_status": "evidence_for_review"})
        # Sorting only within comparable currency/scope/HS series; no invented composite score.
        candidates.sort(key=lambda r: (r["currency"] or "", r["scope"], r["hs_code"], -(r["latest_value"] or 0)))
        return {"status": "ok" if candidates else "no_comparable_data", "demo": demo,
                "candidates": candidates, "fetched": live,
                "warnings": ["国家排序仅用于查看统计证据，不代表保证最优市场。",
                             "世界进口总额与中国对该国出口额分别展示，不直接相加。",
                             "汇总统计单位价值不能直接决定 SKU 报价或利润率。"],
                "next_step": "用户选定国家后才能运行真实客户搜索。"}
