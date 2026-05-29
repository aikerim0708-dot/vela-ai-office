"""
WB API клиент для VELA AI Office.

Поддерживаемые endpoint'ы:
- Statistics-API (продажи, заказы, остатки) — лимит 1 req/min
- Advertising-API (рекламные кампании) — лимит 5 req/sec
- Feedbacks-API (отзывы, вопросы) — лимит 1 req/sec

Все методы возвращают list/dict с распарсенным JSON.
При ошибках возвращают {"error": "..."} вместо exception, чтобы агенты могли
продолжить работу с тем что есть.

Кеш: snapshot обновляется максимум раз в 5 минут (statistics-api лимиты).
"""
from __future__ import annotations
import os
import time
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

STATISTICS_BASE = "https://statistics-api.wildberries.ru"
ADVERT_BASE = "https://advert-api.wildberries.ru"
FEEDBACKS_BASE = "https://feedbacks-api.wildberries.ru"

# Кампании VELA
CAMPAIGN_RAZORS = 29230612    # бритвы
CAMPAIGN_LASHES = 32284868    # ресницы
CAMPAIGNS = [CAMPAIGN_RAZORS, CAMPAIGN_LASHES]

# Кеш snapshot
# Разные TTL для разных endpoint'ов:
#  - statistics-api имеет лимит 1 req/min → кешируем агрессивно (60 мин для sales/stocks/orders)
#  - advert-api 5 req/sec → 10 мин достаточно
#  - feedbacks-api 1 req/sec → 30 мин
CACHE_TTL_DEFAULT = 600       # 10 минут
CACHE_TTL_STATISTICS = 3600   # 60 минут (sales/stocks/orders)
CACHE_TTL_ADVERT = 600        # 10 минут
CACHE_TTL_FEEDBACKS = 1800    # 30 минут
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, fetch_fn, ttl: int = CACHE_TTL_DEFAULT):
    now = time.time()
    if key in _cache:
        ts, value = _cache[key]
        if now - ts < ttl:
            return value
        # Если в кеше HTTP 429 — продлеваем кеш, чтобы не дёргать снова сразу
        if isinstance(value, dict) and "429" in str(value.get("error", "")):
            if now - ts < 120:  # 2 минуты после 429 не дёргаем
                return value
    value = fetch_fn()
    _cache[key] = (now, value)
    return value


def clear_cache():
    _cache.clear()


# ---------------------------------------------------------------------------
# WBClient
# ---------------------------------------------------------------------------


class WBClient:
    def __init__(self, token: str | None = None, timeout: float = 30.0):
        self.token = token or os.environ.get("WB_API_TOKEN", "").strip()
        self.timeout = timeout
        if not self.token:
            raise ValueError("WB_API_TOKEN не задан в env")
        if httpx is None:
            raise ImportError("Установи: pip install httpx")
        self.headers = {"Authorization": self.token}

    # ---------- low-level ----------

    def _get(self, base: str, path: str, params: dict | None = None, retry_429: int = 0) -> Any:
        url = f"{base}{path}"
        for attempt in range(retry_429 + 1):
            try:
                r = httpx.get(url, headers=self.headers, params=params or {}, timeout=self.timeout)
            except Exception as e:
                return {"error": f"{type(e).__name__}: {e}", "url": url}
            if r.status_code == 200:
                return r.json()
            # 429 — WB перегружен/лимит. Ждём Retry-After (или 60с) и пробуем ещё раз.
            if r.status_code == 429 and attempt < retry_429:
                wait_s = float(r.headers.get("Retry-After") or 60)
                time.sleep(min(wait_s, 65))
                continue
            return {"error": f"HTTP {r.status_code}", "url": url, "body": r.text[:300]}

    def _post(self, base: str, path: str, body: Any) -> Any:
        url = f"{base}{path}"
        try:
            r = httpx.post(url, headers=self.headers, json=body, timeout=self.timeout)
            if r.status_code == 200:
                return r.json()
            return {"error": f"HTTP {r.status_code}", "url": url, "body": r.text[:300]}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}", "url": url}

    # ---------- statistics ----------

    def get_orders(self, date_from: str) -> list[dict] | dict:
        """Заказы (включая отменённые) с dateFrom (ISO).

        ВНИМАНИЕ: statistics-api имеет лимит 1 запрос в минуту по этому endpoint.
        Кешируется на 60 минут.
        """
        return _cached(
            f"orders:{date_from}",
            lambda: self._get(STATISTICS_BASE, "/api/v1/supplier/orders", {"dateFrom": date_from}),
            ttl=CACHE_TTL_STATISTICS,
        )

    def get_sales(self, date_from: str) -> list[dict] | dict:
        """Продажи (выкупленные заказы) с dateFrom (ISO)."""
        return _cached(
            f"sales:{date_from}",
            lambda: self._get(STATISTICS_BASE, "/api/v1/supplier/sales", {"dateFrom": date_from}),
            ttl=CACHE_TTL_STATISTICS,
        )

    def get_stocks(self, date_from: str | None = None) -> list[dict] | dict:
        """Остатки на складах FBO/FBS на момент запроса."""
        if not date_from:
            date_from = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00")
        return _cached(
            f"stocks:{date_from}",
            lambda: self._get(STATISTICS_BASE, "/api/v1/supplier/stocks", {"dateFrom": date_from}),
            ttl=CACHE_TTL_STATISTICS,
        )

    # ---------- advertising ----------

    def list_adverts(self) -> Any:
        """Список всех рекламных кампаний продавца. /adv/v1/promotion/count актуален в 2026."""
        return _cached("adverts_list", lambda: self._get(ADVERT_BASE, "/adv/v1/promotion/count"), ttl=CACHE_TTL_ADVERT)

    def get_advert_info(self, campaign_ids: list[int]) -> Any:
        """Детали по кампаниям (статусы, бюджет, тип) через /adv/v1/promotion/adverts."""
        return _cached(
            f"advert_info:{','.join(map(str, campaign_ids))}",
            lambda: self._post(ADVERT_BASE, "/adv/v1/promotion/adverts", campaign_ids),
            ttl=CACHE_TTL_ADVERT,
        )

    def get_campaign_stats(self, campaign_ids: list[int], date_from: str, date_to: str) -> Any:
        """Полная статистика по списку кампаний за период.

        date_from / date_to — формат YYYY-MM-DD.

        ВАЖНО (29.05.2026): /adv/v3/fullstats принимает ТОЛЬКО GET.
        POST → 405 Method Not Allowed (Allow: GET, HEAD). Параметр `ids`
        повторяется для каждой кампании, даты — dateFrom/dateTo в query.
        (v2 удалён → 404.) Метод синхронизирован с wb_client.get_campaign_fullstats.
        """
        # httpx умеет повторять query-параметр через список кортежей
        params: list[tuple[str, Any]] = [("ids", int(cid)) for cid in campaign_ids]
        params.append(("dateFrom", date_from))
        params.append(("dateTo", date_to))
        cache_key = f"campaign_stats:{','.join(map(str, campaign_ids))}:{date_from}:{date_to}"

        return _cached(
            cache_key,
            lambda: self._get(ADVERT_BASE, "/adv/v3/fullstats", params, retry_429=1),
            ttl=CACHE_TTL_ADVERT,
        )

    # ---------- feedbacks ----------

    def get_feedbacks(self, is_answered: bool = False, take: int = 50, skip: int = 0,
                      order: str = "dateDesc") -> Any:
        """Отзывы. По умолчанию — неотвеченные за всё время.

        Требует scope «Отзывы и вопросы» на WB-токене. Если ловим 401 —
        кешируем НАВСЕГДА чтобы не мучать API (пока пользователь не пересоздаст токен).
        """
        params = {
            "isAnswered": str(is_answered).lower(),
            "take": take,
            "skip": skip,
            "order": order,
        }
        return _cached(
            f"feedbacks:{is_answered}:{take}:{skip}",
            lambda: self._get(FEEDBACKS_BASE, "/api/v1/feedbacks", params),
            ttl=CACHE_TTL_FEEDBACKS,
        )

    def get_questions(self, is_answered: bool = False, take: int = 50, skip: int = 0) -> Any:
        params = {
            "isAnswered": str(is_answered).lower(),
            "take": take,
            "skip": skip,
        }
        return _cached(
            f"questions:{is_answered}:{take}:{skip}",
            lambda: self._get(FEEDBACKS_BASE, "/api/v1/questions", params),
            ttl=CACHE_TTL_FEEDBACKS,
        )


# ---------------------------------------------------------------------------
# Snapshot — что нужно для утреннего разбора
# ---------------------------------------------------------------------------


def yesterday_iso() -> str:
    """Вчерашняя дата в формате 2026-05-26T00:00:00."""
    d = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
    return d


def date_str(days_ago: int = 0) -> str:
    """YYYY-MM-DD для adv-api fullstats."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def aggregate_orders(orders: list[dict]) -> dict:
    """Сводка по заказам: count, sum, по SKU, по кластерам."""
    if not isinstance(orders, list):
        return {"error": "не получили данные заказов", "raw": orders}

    by_supplier_article: dict[str, dict] = {}
    total_count = 0
    total_sum = 0.0
    cancelled = 0

    for o in orders:
        total_count += 1
        if o.get("isCancel"):
            cancelled += 1
            continue
        sku = o.get("supplierArticle") or o.get("nmId", "?")
        price = float(o.get("priceWithDisc", 0) or 0)
        total_sum += price
        if sku not in by_supplier_article:
            by_supplier_article[sku] = {"count": 0, "sum": 0.0, "nm_id": o.get("nmId")}
        by_supplier_article[sku]["count"] += 1
        by_supplier_article[sku]["sum"] += price

    top = sorted(by_supplier_article.items(), key=lambda kv: kv[1]["sum"], reverse=True)[:10]
    return {
        "total_orders": total_count,
        "cancelled": cancelled,
        "revenue_orders_total": round(total_sum, 2),
        "top10_by_revenue": [
            {"sku": sku, "nmId": v["nm_id"], "count": v["count"], "sum": round(v["sum"], 2)}
            for sku, v in top
        ],
    }


def aggregate_sales(sales: list[dict]) -> dict:
    if not isinstance(sales, list):
        return {"error": "не получили данные продаж", "raw": sales}

    total = 0.0
    count = 0
    for s in sales:
        count += 1
        total += float(s.get("forPay", 0) or 0)

    return {
        "sales_count": count,
        "total_for_pay": round(total, 2),
    }


def aggregate_stocks(stocks: list[dict]) -> dict:
    if not isinstance(stocks, list):
        return {"error": "не получили данные остатков", "raw": stocks}

    by_sku: dict[str, int] = {}
    warehouses: dict[str, int] = {}

    for s in stocks:
        sku = s.get("supplierArticle") or s.get("nmId", "?")
        qty = int(s.get("quantity", 0))
        wh = s.get("warehouseName", "?")
        by_sku[sku] = by_sku.get(sku, 0) + qty
        warehouses[wh] = warehouses.get(wh, 0) + qty

    top_sku = sorted(by_sku.items(), key=lambda kv: kv[1], reverse=True)[:15]
    return {
        "total_units": sum(by_sku.values()),
        "skus_count": len(by_sku),
        "top15_by_quantity": [{"sku": sku, "qty": qty} for sku, qty in top_sku],
        "by_warehouse": warehouses,
    }


def aggregate_campaign(stats: Any, campaign_id: int) -> dict:
    """Из ответа fullstats извлечь суммарные показы / клики / расход / выручка / ДРР."""
    if not isinstance(stats, list):
        return {"error": "не получили stats", "raw": stats}

    for item in stats:
        if item.get("advertId") != campaign_id:
            continue
        views = item.get("views", 0)
        clicks = item.get("clicks", 0)
        sum_spend = float(item.get("sum", 0) or 0)
        atbs = item.get("atbs", 0)
        orders = item.get("orders", 0)
        shks = item.get("shks", 0)
        sum_price = float(item.get("sum_price", 0) or 0)
        drr = round(sum_spend / sum_price * 100, 2) if sum_price else None
        ctr = round(clicks / views * 100, 2) if views else None
        cr = round(orders / clicks * 100, 2) if clicks else None
        cpc = round(sum_spend / clicks, 2) if clicks else None
        return {
            "campaign_id": campaign_id,
            "views": views,
            "clicks": clicks,
            "ctr_pct": ctr,
            "atbs": atbs,
            "orders": orders,
            "cr_pct": cr,
            "shks": shks,
            "spend_rub": round(sum_spend, 2),
            "revenue_ad_rub": round(sum_price, 2),
            "drr_pct": drr,
            "cpc_rub": cpc,
        }
    return {"error": f"кампания {campaign_id} не найдена в ответе"}


def aggregate_feedbacks(feedbacks_resp: Any) -> dict:
    """Сводка по отзывам: всего, по звёздам, неотвеченные 1-2★."""
    if not isinstance(feedbacks_resp, dict) or "data" not in feedbacks_resp:
        return {"error": "не получили отзывы", "raw": feedbacks_resp}

    data = feedbacks_resp.get("data", {})
    feedbacks = data.get("feedbacks") if isinstance(data, dict) else None
    if not isinstance(feedbacks, list):
        return {"error": "нет feedbacks в data", "raw": data}

    by_star = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    critical = []
    for fb in feedbacks:
        star = fb.get("productValuation") or 0
        if star in by_star:
            by_star[star] += 1
        if star in (1, 2):
            critical.append({
                "id": fb.get("id"),
                "star": star,
                "sku": fb.get("productDetails", {}).get("supplierArticle"),
                "text": (fb.get("text") or "")[:200],
                "createdDate": fb.get("createdDate"),
            })

    return {
        "total": len(feedbacks),
        "by_star": by_star,
        "critical_count": len(critical),
        "critical_samples": critical[:5],
    }


def fetch_snapshot(client: WBClient | None = None) -> dict:
    """Полный snapshot WB за вчера + текущие остатки + рекламные кампании.

    Может быть медленным первый раз (~10-20 сек из-за rate limits WB),
    но кешируется на 5 минут.
    """
    if client is None:
        try:
            client = WBClient()
        except (ValueError, ImportError) as e:
            return {"error": str(e), "ts": datetime.now(timezone.utc).isoformat()}

    yesterday = yesterday_iso()
    today_str = date_str(0)
    yest_str = date_str(1)

    orders_raw = client.get_orders(yesterday)
    sales_raw = client.get_sales(yesterday)
    stocks_raw = client.get_stocks()
    campaigns_raw = client.get_campaign_stats(CAMPAIGNS, yest_str, today_str)
    feedbacks_raw = client.get_feedbacks(is_answered=False, take=30)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "yesterday": yesterday,
        "orders": aggregate_orders(orders_raw),
        "sales": aggregate_sales(sales_raw),
        "stocks": aggregate_stocks(stocks_raw),
        "campaigns": {
            "razors_29230612": aggregate_campaign(campaigns_raw, CAMPAIGN_RAZORS),
            "lashes_32284868": aggregate_campaign(campaigns_raw, CAMPAIGN_LASHES),
        },
        "feedbacks": aggregate_feedbacks(feedbacks_raw),
    }


def snapshot_for_agent_context(snapshot: dict) -> str:
    """Превращает snapshot в текстовый блок для system-промпта агента."""
    if "error" in snapshot:
        return f"## ⚠️ WB API недоступен\n{snapshot.get('error')}"

    lines = ["## 📊 Свежие данные с WB API (snapshot)\n"]
    lines.append(f"Время снимка: {snapshot.get('ts')}")
    lines.append(f"Период данных: с {snapshot.get('yesterday')}")

    # Краткий статус по источникам
    statuses = []
    for key, label in [("orders", "Заказы"), ("sales", "Продажи"), ("stocks", "Остатки"),
                        ("campaigns", "Реклама"), ("feedbacks", "Отзывы")]:
        block = snapshot.get(key, {})
        if isinstance(block, dict):
            if "error" in block:
                statuses.append(f"{label} ❌")
            else:
                statuses.append(f"{label} ✅")
    lines.append("Источники: " + " · ".join(statuses) + "\n")

    # Заказы
    o = snapshot.get("orders", {})
    if "error" not in o:
        lines.append("### Заказы вчера")
        lines.append(f"- Всего: {o.get('total_orders')} (отменено {o.get('cancelled')})")
        lines.append(f"- Выручка по заказам: {o.get('revenue_orders_total'):,.0f} ₽")
        top = o.get("top10_by_revenue", [])
        if top:
            lines.append("- Топ-10 SKU по выручке:")
            for t in top:
                lines.append(f"   • {t['sku']} (nmId {t['nmId']}): {t['count']} заказов, {t['sum']:,.0f} ₽")

    # Продажи
    s = snapshot.get("sales", {})
    if "error" not in s:
        lines.append("\n### Продажи (выкупленные) вчера")
        lines.append(f"- Сделок: {s.get('sales_count')}, к оплате: {s.get('total_for_pay'):,.0f} ₽")

    # Остатки
    st = snapshot.get("stocks", {})
    if "error" not in st:
        lines.append("\n### Остатки на складах")
        lines.append(f"- Всего единиц: {st.get('total_units'):,}")
        lines.append(f"- SKU в наличии: {st.get('skus_count')}")
        wh = st.get("by_warehouse", {})
        if wh:
            top_wh = sorted(wh.items(), key=lambda kv: kv[1], reverse=True)[:5]
            lines.append("- Топ-5 складов: " + ", ".join(f"{w} ({q})" for w, q in top_wh))

    # Реклама
    camps = snapshot.get("campaigns", {})
    for label, c in camps.items():
        if isinstance(c, dict) and "error" not in c:
            lines.append(f"\n### Кампания {label}")
            lines.append(f"- Расход: {c.get('spend_rub'):,.0f} ₽, выручка-AD: {c.get('revenue_ad_rub'):,.0f} ₽")
            lines.append(f"- ДРР: {c.get('drr_pct')}% · CTR: {c.get('ctr_pct')}% · CR: {c.get('cr_pct')}% · CPC: {c.get('cpc_rub')} ₽")
            lines.append(f"- Показы: {c.get('views'):,} · Клики: {c.get('clicks'):,} · В корзину: {c.get('atbs')} · Заказы: {c.get('orders')}")

    # Отзывы
    f = snapshot.get("feedbacks", {})
    if "error" not in f:
        lines.append("\n### Неотвеченные отзывы")
        lines.append(f"- Всего: {f.get('total')} (1-2★: {f.get('critical_count')})")
        by_star = f.get("by_star", {})
        lines.append(f"- По звёздам: " + ", ".join(f"{s}★ {by_star.get(s, 0)}" for s in [5, 4, 3, 2, 1]))
        for c in f.get("critical_samples", [])[:3]:
            lines.append(f"   • #{c['id']} {c['star']}★ ({c['sku']}): {c['text'][:120]}…")

    return "\n".join(lines)
