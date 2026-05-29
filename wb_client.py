"""
WB API client — обёртки для Wildberries Seller / Advertising / Statistics API.

Архитектура: 3 токена, маршрутизация по hostname.
Полная матрица: docs/wb_tokens_matrix.md

    WB_TOKEN_READ    — Статистика + Аналитика + Финансы (read-only)
    WB_TOKEN_ADS     — Продвижение (read+write)
    WB_TOKEN_MANAGE  — Контент + Отзывы + Цены и скидки + Поставки + Маркетплейс

Логика выбора токена — по host endpoint, а НЕ по агенту. Один host = один scope = один токен.

Использование:
    from wb_client import WBClient
    wb = WBClient()                                    # читает 3 токена из env
    campaigns = wb.list_campaigns()
    stats = wb.get_campaign_fullstats(campaign_ids=[29230612, 32284868], days=1)
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx


# ---------- Базовые URL официальных API WB ----------
STATS_BASE = "https://statistics-api.wildberries.ru"
ANALYTICS_BASE = "https://seller-analytics-api.wildberries.ru"
FINANCE_BASE = "https://finance-api.wildberries.ru"
ADV_BASE = "https://advert-api.wildberries.ru"
CONTENT_BASE = "https://content-api.wildberries.ru"
FEEDBACK_BASE = "https://feedbacks-api.wildberries.ru"
DISCOUNTS_BASE = "https://discounts-prices-api.wildberries.ru"
SUPPLIES_BASE = "https://supplies-api.wildberries.ru"
MARKETPLACE_BASE = "https://marketplace-api.wildberries.ru"

# Маппинг host → название токена (READ / ADS / MANAGE)
# Не "токен на агента", а "токен на scope". Зафиксировано в docs/wb_tokens_matrix.md
HOST_TO_TOKEN: Dict[str, str] = {
    "statistics-api.wildberries.ru":      "READ",
    "seller-analytics-api.wildberries.ru": "READ",
    "finance-api.wildberries.ru":         "READ",
    "advert-api.wildberries.ru":          "ADS",
    "content-api.wildberries.ru":         "MANAGE",
    "feedbacks-api.wildberries.ru":       "MANAGE",
    "discounts-prices-api.wildberries.ru": "MANAGE",
    "supplies-api.wildberries.ru":        "MANAGE",
    "marketplace-api.wildberries.ru":     "MANAGE",
}


class WBAPIError(Exception):
    """Ошибка WB API. message содержит статус и ответ."""

    def __init__(self, status: int, body: str, endpoint: str):
        super().__init__(f"WB API {endpoint} → {status}: {body[:300]}")
        self.status = status
        self.body = body
        self.endpoint = endpoint


def _host_of(url: str) -> str:
    """Достаёт host из URL без зависимостей на urllib."""
    # https://x.y.z/path → x.y.z
    after_scheme = url.split("://", 1)[-1]
    return after_scheme.split("/", 1)[0]


class WBClient:
    """Минимальный синхронный клиент WB с маршрутизацией по 3 токенам.

    Лимиты WB (на 2026):
    - Adv API: ~100 req/min, /adv/v3/fullstats — 1 req/min
    - Statistics: ~1 req/min на тяжёлые отчёты, ~300 req/min на лёгкие
    - Content / Feedbacks: ~10 req/sec
    """

    def __init__(
        self,
        token_read: Optional[str] = None,
        token_ads: Optional[str] = None,
        token_manage: Optional[str] = None,
        timeout: float = 30.0,
    ):
        # Fallback цепочка: явный аргумент → новая переменная → старая WB_API_TOKEN → ""
        legacy = os.environ.get("WB_API_TOKEN", "").strip()
        self.tokens: Dict[str, str] = {
            "READ":   (token_read   or os.environ.get("WB_TOKEN_READ", "")   or legacy).strip(),
            "ADS":    (token_ads    or os.environ.get("WB_TOKEN_ADS", "")    or legacy).strip(),
            "MANAGE": (token_manage or os.environ.get("WB_TOKEN_MANAGE", "") or legacy).strip(),
        }
        self.timeout = timeout
        self._cache: Dict[Tuple, Tuple[float, Any]] = {}
        self._cache_ttl = 300.0
        self._ping_cache: Optional[dict] = None
        self._ping_cache_until: float = 0.0

    # ---------- утилиты ----------
    def _token_for(self, url: str) -> Tuple[str, str]:
        """Возвращает (имя токена, значение токена) для данного URL.

        Если host не найден в маппинге — fallback на READ.
        Если конкретный токен пустой — пробуем остальные по приоритету ADS/MANAGE/READ.
        """
        host = _host_of(url)
        name = HOST_TO_TOKEN.get(host, "READ")
        tok = self.tokens.get(name, "")
        if not tok or tok.startswith("PUT_YOUR"):
            for fallback in ("READ", "ADS", "MANAGE"):
                if self.tokens.get(fallback) and not self.tokens[fallback].startswith("PUT_YOUR"):
                    return fallback, self.tokens[fallback]
        return name, tok

    def _headers(self, url: str) -> Dict[str, str]:
        _, tok = self._token_for(url)
        return {
            "Authorization": tok,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _has_any_token(self) -> bool:
        return any(
            bool(v) and not v.startswith("PUT_YOUR")
            for v in self.tokens.values()
        )

    def _cache_get(self, key: Tuple) -> Any:
        rec = self._cache.get(key)
        if not rec:
            return None
        ts, val = rec
        if time.time() - ts > self._cache_ttl:
            self._cache.pop(key, None)
            return None
        return val

    def _cache_put(self, key: Tuple, value: Any) -> None:
        self._cache[key] = (time.time(), value)

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json_body: Any = None,
        cache: bool = True,
    ) -> Any:
        token_name, token_value = self._token_for(url)
        if not token_value or token_value.startswith("PUT_YOUR"):
            raise WBAPIError(
                401,
                "WB_TOKEN_{} не задан в .env. Положи токен и перезапусти uvicorn.".format(token_name),
                url,
            )

        cache_key = (method, url, repr(params), repr(json_body))
        if cache:
            hit = self._cache_get(cache_key)
            if hit is not None:
                return hit

        last_r = None
        for attempt in range(3):
            with httpx.Client(timeout=self.timeout) as client:
                r = client.request(
                    method,
                    url,
                    headers=self._headers(url),
                    params=params,
                    json=json_body,
                )
            last_r = r
            if r.status_code != 429:
                break
            wait_s = float(r.headers.get("Retry-After") or (5 * (attempt + 1)))
            time.sleep(min(wait_s, 30))

        r = last_r
        if r.status_code >= 400:
            raise WBAPIError(r.status_code, r.text, url)

        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}

        if cache:
            self._cache_put(cache_key, data)
        return data

    # ---------- здоровье / проверка токенов ----------
    def ping(self) -> dict:
        """Проверка живости всех 3 токенов одним вызовом.

        Возвращает {ok, tokens: {READ: {...}, ADS: {...}, MANAGE: {...}}}
        Кэш 5 минут — WB агрессивно блокирует частые проверки (429).
        """
        if self._ping_cache and time.time() < self._ping_cache_until:
            return {**self._ping_cache, "cached": True}

        result: Dict[str, Any] = {"ok": True, "tokens": {}, "scopes": {}}

        # ────── 1 пробинг на токен (auth-check) ──────
        result["tokens"]["READ"] = self._probe(
            "GET",
            f"{STATS_BASE}/api/v1/supplier/sales",
            params={"dateFrom": _yesterday_iso(), "flag": 0},
        )
        result["tokens"]["ADS"] = self._probe(
            "GET",
            f"{ADV_BASE}/adv/v1/promotion/count",
        )
        result["tokens"]["MANAGE"] = self._probe(
            "GET",
            f"{FEEDBACK_BASE}/api/v1/feedbacks/count",
            params={"isAnswered": "false"},
        )

        # ────── Пробинги на каждый scope (понимаем какие галочки реально стоят) ──────
        # READ scopes
        result["scopes"]["Статистика"] = result["tokens"]["READ"]
        result["scopes"]["Аналитика"] = self._probe(
            "GET",
            f"{ANALYTICS_BASE}/api/v1/paid_storage",
            params={"dateFrom": _yesterday_iso(), "dateTo": _yesterday_iso()},
        )
        result["scopes"]["Финансы"] = self._probe(
            "GET",
            f"{FINANCE_BASE}/api/v5/supplier/reportDetailByPeriod",
            params={"dateFrom": _yesterday_iso(), "dateTo": _yesterday_iso(), "limit": 1, "rrdid": 0},
        )

        # ADS scopes
        result["scopes"]["Продвижение"] = result["tokens"]["ADS"]

        # MANAGE scopes
        result["scopes"]["Контент"] = self._probe(
            "POST",
            f"{CONTENT_BASE}/content/v2/get/cards/list",
            params=None,
        )
        result["scopes"]["Вопросы и отзывы"] = result["tokens"]["MANAGE"]
        result["scopes"]["Цены и скидки"] = self._probe(
            "GET",
            f"{DISCOUNTS_BASE}/api/v2/list/goods/filter",
            params={"limit": 1, "offset": 0},
        )
        result["scopes"]["Поставки"] = self._probe(
            "GET",
            f"{SUPPLIES_BASE}/api/v1/supplies",
            params={"limit": 1, "next": 0},
        )
        result["scopes"]["Маркетплейс"] = self._probe(
            "GET",
            f"{MARKETPLACE_BASE}/api/v3/warehouses",
        )

        result["ok"] = all(t.get("ok") for t in result["tokens"].values())
        self._ping_cache = result
        self._ping_cache_until = time.time() + 300.0
        return result

    def _probe(self, method: str, url: str, params: Optional[dict] = None) -> dict:
        """Безопасный пробник: возвращает {ok, status, error?} вместо исключения.

        Трактовка статусов:
          200 → токен валидный, scope разрешён, всё ок
          429 → токен ВАЛИДНЫЙ (auth+scope прошли), WB просто перегружен —
                это успех для health-check, маркируем rate_limited:true
          401/403 → токен битый или не хватает scope — это реальная проблема
        """
        token_name, _ = self._token_for(url)
        try:
            self._request(method, url, params=params, cache=False)
            return {"ok": True, "status": 200, "token": token_name}
        except WBAPIError as e:
            if e.status == 429:
                # auth прошла, scope ок, просто rate limit — токен живой
                return {
                    "ok": True,
                    "status": 429,
                    "token": token_name,
                    "rate_limited": True,
                    "note": "WB rate limit на этот endpoint, токен валидный (auth прошёл)",
                }
            return {
                "ok": False,
                "status": e.status,
                "token": token_name,
                "error": str(e)[:200],
            }

    # ---------- РЕКЛАМА (Лео) ----------
    def list_campaigns(self) -> List[dict]:
        """GET /adv/v1/promotion/count — все рекламные кампании."""
        data = self._request("GET", f"{ADV_BASE}/adv/v1/promotion/count")
        flat: List[dict] = []
        for group in data.get("adverts", []) or []:
            for item in group.get("advert_list", []) or []:
                flat.append({
                    "advert_id": item.get("advertId"),
                    "change_time": item.get("changeTime"),
                    "type": group.get("type"),
                    "status": group.get("status"),
                })
        return flat

    def get_campaign_info(self, campaign_ids: List[int]) -> List[dict]:
        """POST /adv/v1/promotion/adverts — детали кампаний (имя, бюджет, кластеры).

        Это всё ещё POST (а не GET) — проверено 28.05.2026, эндпоинт live.
        """
        body = [int(x) for x in campaign_ids]
        return self._request(
            "POST", f"{ADV_BASE}/adv/v1/promotion/adverts", json_body=body
        )

    def get_campaign_fullstats(
        self,
        campaign_ids: List[int],
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        days: int = 1,
    ) -> List[dict]:
        """GET /adv/v3/fullstats — статистика кампаний по дням с разбивкой по кластерам.

        ВАЖНО (28.05.2026):
        - /adv/v2/fullstats — удалён (404)
        - /adv/v3/fullstats — только GET (POST → 405 Method Not Allowed)
        - Параметр называется `ids` (множественное), повторяется для каждой кампании

        WB ограничение: ~1 req/min на этот endpoint, период до 31 дня, только 3 мес назад.
        """
        if not date_from or not date_to:
            today = datetime.now(timezone.utc).date()
            date_to = today.isoformat()
            date_from = (today - timedelta(days=max(0, days - 1))).isoformat()

        # httpx умеет повторять параметр: params=[("ids",a),("ids",b)]
        params: List[Tuple[str, Any]] = [("ids", int(cid)) for cid in campaign_ids]
        params.append(("dateFrom", date_from))
        params.append(("dateTo", date_to))

        return self._request(
            "GET",
            f"{ADV_BASE}/adv/v3/fullstats",
            params=params,
            cache=False,
        )

    # ---------- ПРОДАЖИ / ЗАКАЗЫ / ОСТАТКИ (Зара, Анна) ----------
    def get_sales(self, date_from: str, flag: int = 0) -> List[dict]:
        """GET /api/v1/supplier/sales — продажи (выкупы)."""
        return self._request(
            "GET",
            f"{STATS_BASE}/api/v1/supplier/sales",
            params={"dateFrom": date_from, "flag": flag},
        )

    def get_orders(self, date_from: str, flag: int = 0) -> List[dict]:
        """GET /api/v1/supplier/orders — заказы (до выкупа)."""
        return self._request(
            "GET",
            f"{STATS_BASE}/api/v1/supplier/orders",
            params={"dateFrom": date_from, "flag": flag},
        )

    def get_stocks(self, date_from: str = "2019-06-20") -> List[dict]:
        """GET /api/v1/supplier/stocks — остатки на складах WB."""
        return self._request(
            "GET",
            f"{STATS_BASE}/api/v1/supplier/stocks",
            params={"dateFrom": date_from},
        )

    # ---------- ОТЗЫВЫ (Ева) ----------
    def get_feedbacks(self, is_answered: bool = False, take: int = 50, skip: int = 0) -> dict:
        """GET /api/v1/feedbacks — список отзывов."""
        return self._request(
            "GET",
            f"{FEEDBACK_BASE}/api/v1/feedbacks",
            params={
                "isAnswered": str(is_answered).lower(),
                "take": take,
                "skip": skip,
            },
        )


# ---------- ПОЛЕЗНЫЕ АГРЕГАТЫ для Лео ----------
def summarize_campaign_fullstats(stats: List[dict]) -> List[dict]:
    """Превращает сырые данные WB в плоскую сводку для Лео."""
    out: List[dict] = []
    for camp in stats or []:
        cid = camp.get("advertId")
        days = camp.get("days", []) or []

        sum_views = sum(d.get("views", 0) for d in days)
        sum_clicks = sum(d.get("clicks", 0) for d in days)
        sum_orders = sum(d.get("orders", 0) for d in days)
        sum_cost = sum(d.get("sum", 0) for d in days)
        sum_sum_price = sum(d.get("sum_price", 0) for d in days)

        ctr = (sum_clicks / sum_views * 100.0) if sum_views else 0.0
        cr = (sum_orders / sum_clicks * 100.0) if sum_clicks else 0.0
        drr = (sum_cost / sum_sum_price * 100.0) if sum_sum_price else 0.0

        cluster_agg: Dict[str, dict] = {}
        for d in days:
            for app in d.get("apps", []) or []:
                for nm in app.get("nm", []) or []:
                    name = nm.get("name") or str(nm.get("nmId") or "?")
                    rec = cluster_agg.setdefault(
                        name,
                        {"views": 0, "clicks": 0, "orders": 0, "sum": 0.0, "sum_price": 0.0},
                    )
                    rec["views"] += nm.get("views", 0)
                    rec["clicks"] += nm.get("clicks", 0)
                    rec["orders"] += nm.get("orders", 0)
                    rec["sum"] += nm.get("sum", 0)
                    rec["sum_price"] += nm.get("sum_price", 0)

        clusters = []
        for name, r in cluster_agg.items():
            c_ctr = (r["clicks"] / r["views"] * 100.0) if r["views"] else 0.0
            c_cr = (r["orders"] / r["clicks"] * 100.0) if r["clicks"] else 0.0
            c_drr = (r["sum"] / r["sum_price"] * 100.0) if r["sum_price"] else 0.0
            clusters.append({
                "name": name,
                "views": r["views"],
                "clicks": r["clicks"],
                "orders": r["orders"],
                "ctr": round(c_ctr, 2),
                "cr": round(c_cr, 2),
                "cost": round(r["sum"], 2),
                "revenue_ad": round(r["sum_price"], 2),
                "drr": round(c_drr, 2),
            })
        clusters.sort(key=lambda x: x["cost"], reverse=True)

        out.append({
            "campaign_id": cid,
            "days_count": len(days),
            "views": sum_views,
            "clicks": sum_clicks,
            "orders": sum_orders,
            "ctr": round(ctr, 2),
            "cr": round(cr, 2),
            "cost": round(sum_cost, 2),
            "revenue_ad": round(sum_sum_price, 2),
            "drr": round(drr, 2),
            "clusters_top": clusters[:15],
        })
    return out


def _yesterday_iso() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
