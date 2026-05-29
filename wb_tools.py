"""
Каталог инструментов WB для агентов VELA.

Каждый агент получает свой набор tools — Claude сам решает когда дёрнуть.
Диспетчер dispatch_tool_call вызывает соответствующую функцию wb_client + загрузчик Excel.

Минимизируем поверхность атаки: инструменты ТОЛЬКО ЧИТАЮТ. Никаких изменений
кампаний/цен/ставок — это всегда через approval Айкерим.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from wb_client import WBClient, summarize_campaign_fullstats


# Один shared клиент на процесс — токен из env
_wb_singleton: WBClient | None = None


def _wb() -> WBClient:
    global _wb_singleton
    if _wb_singleton is None:
        _wb_singleton = WBClient()
    return _wb_singleton


# ---------------------------------------------------------------------------
# Инструменты для Лео (реклама)
# ---------------------------------------------------------------------------
LEO_TOOLS: list[dict] = [
    {
        "name": "wb_list_campaigns",
        "description": (
            "Список всех рекламных кампаний продавца. "
            "Используй когда нужно проверить какие кампании активны/на паузе/завершены. "
            "Возвращает массив {advert_id, status, type, change_time}. "
            "Статус: 9=идут показы, 11=пауза, 7=завершена, 4=готова, 8=отказался."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "wb_campaign_info",
        "description": (
            "Полная инфа по конкретным кампаниям: имя, дневной бюджет, СПП, привязанные SKU и кластеры. "
            "Используй когда нужно понять что внутри кампании."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Список ID кампаний. Например [29230612, 32284868]",
                }
            },
            "required": ["campaign_ids"],
        },
    },
    {
        "name": "wb_campaign_stats",
        "description": (
            "Статистика по кампаниям за период: расход, выручка с рекламы, ДРР, CTR, CR, "
            "разбивка по кластерам (booster-словам/SKU). "
            "ЭТО ТВОЙ ОСНОВНОЙ ИНСТРУМЕНТ для утреннего разбора. "
            "Если date_from/date_to не указаны — берёт последние `days` дней (по умолчанию 1 = вчера)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "ID кампаний, например [29230612, 32284868]",
                },
                "date_from": {
                    "type": "string",
                    "description": "Начало периода YYYY-MM-DD. Опционально.",
                },
                "date_to": {
                    "type": "string",
                    "description": "Конец периода YYYY-MM-DD. Опционально.",
                },
                "days": {
                    "type": "integer",
                    "description": "Сколько последних дней (если date_from/to не заданы). По умолчанию 1.",
                    "default": 1,
                },
            },
            "required": ["campaign_ids"],
        },
    },
]


# ---------------------------------------------------------------------------
# Инструменты для Анны (склады / поставки)
# ---------------------------------------------------------------------------
ANNA_TOOLS: list[dict] = [
    {
        "name": "wb_stocks",
        "description": (
            "Остатки по всем SKU на всех складах WB. Возвращает массив "
            "{supplierArticle, warehouseName, quantity, ...}. Используй для расчёта DOS и OOS-риска."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "wb_sales_recent",
        "description": (
            "Заказы (продажи) за последние N дней. Нужно для расчёта velocity (скорость продаж SKU) "
            "перед прогнозом OOS. По умолчанию 7 дней."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "За сколько дней. Дефолт 7.",
                    "default": 7,
                }
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Инструменты для Зары (финансы)
# ---------------------------------------------------------------------------
ZARA_TOOLS: list[dict] = [
    {
        "name": "wb_sales_recent",
        "description": (
            "Заказы (продажи) за последние N дней — для расчёта выручки, среднего чека, ДРР по дням."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7},
            },
        },
    },
    {
        "name": "wb_campaign_stats",
        "description": (
            "Расход и выручка рекламы за период — нужно Заре для CAC и общего ДРР."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_ids": {"type": "array", "items": {"type": "integer"}},
                "days": {"type": "integer", "default": 7},
            },
            "required": ["campaign_ids"],
        },
    },
]


# ---------------------------------------------------------------------------
# Инструменты для Евы (отзывы)
# ---------------------------------------------------------------------------
EVA_TOOLS: list[dict] = [
    {
        "name": "wb_unanswered_feedbacks",
        "description": (
            "Новые отзывы без ответа. Возвращает массив с текстом, оценкой, SKU. "
            "Используй для поиска паттернов негатива."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "take": {"type": "integer", "default": 50},
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Общий инструмент для всех — чтение загруженного Excel/CSV
# ---------------------------------------------------------------------------
UPLOADS_DIR = Path(__file__).parent.parent / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

COMMON_TOOLS: list[dict] = [
    {
        "name": "read_uploaded_file",
        "description": (
            "Прочитать файл который Айкерим загрузила в офис (Excel .xlsx, .xls или CSV). "
            "Используй когда она прислала экспорт из WB Seller, Wildbox или MPSTATS. "
            "Возвращает первые 200 строк + заголовки + сводку по числовым колонкам."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Имя файла из папки uploads. Если не уверен — вызови list_uploaded_files.",
                },
                "sheet": {
                    "type": "string",
                    "description": "Имя листа (для .xlsx). Опционально.",
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Сколько строк прочитать. Дефолт 200.",
                    "default": 200,
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": "list_uploaded_files",
        "description": "Список файлов которые Айкерим загрузила в офис. Возвращает имена и размер.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ---------------------------------------------------------------------------
# Маппинг: какой агент какие инструменты получает
# ---------------------------------------------------------------------------
def get_tools_for_agent(slug: str) -> list[dict]:
    base = list(COMMON_TOOLS)  # всем доступны загруженные файлы
    if slug == "leo":
        return LEO_TOOLS + base
    if slug == "anna":
        return ANNA_TOOLS + base
    if slug == "zara":
        return ZARA_TOOLS + base
    if slug == "eva":
        return EVA_TOOLS + base
    # Макс — без прямого доступа, он делегирует
    return []


# ---------------------------------------------------------------------------
# Диспетчер вызовов инструментов
# ---------------------------------------------------------------------------
def dispatch_tool_call(name: str, args: dict) -> Any:
    """Вызывает соответствующую функцию. Все ошибки превращаются в {error:...}.

    Возвращаемое значение сериализуется в JSON и отдаётся Claude как tool_result.
    """
    wb = _wb()

    if name == "wb_list_campaigns":
        return {"campaigns": wb.list_campaigns()}

    if name == "wb_campaign_info":
        ids = [int(x) for x in (args.get("campaign_ids") or [])]
        if not ids:
            return {"error": "campaign_ids пуст"}
        return {"campaigns": wb.get_campaign_info(ids)}

    if name == "wb_campaign_stats":
        ids = [int(x) for x in (args.get("campaign_ids") or [])]
        if not ids:
            return {"error": "campaign_ids пуст"}
        date_from = args.get("date_from")
        date_to = args.get("date_to")
        days = int(args.get("days") or 1)
        raw = wb.get_campaign_fullstats(
            campaign_ids=ids, date_from=date_from, date_to=date_to, days=days
        )
        summary = summarize_campaign_fullstats(raw)
        return {"campaigns_summary": summary, "raw_count": len(raw) if raw else 0}

    if name == "wb_stocks":
        stocks = wb.get_stocks()
        # Большой ответ — режем агрегатом по SKU чтобы не переполнить контекст
        agg: dict[str, dict] = {}
        for s in stocks:
            sku = s.get("supplierArticle") or s.get("nmId") or "?"
            rec = agg.setdefault(str(sku), {"total": 0, "warehouses": {}})
            rec["total"] += s.get("quantity", 0)
            wh = s.get("warehouseName", "?")
            rec["warehouses"][wh] = rec["warehouses"].get(wh, 0) + s.get("quantity", 0)
        # Топ 30 по остатку
        top = sorted(agg.items(), key=lambda x: x[1]["total"], reverse=True)[:30]
        return {"stocks_top": [{"sku": k, **v} for k, v in top], "sku_count": len(agg)}

    if name == "wb_sales_recent":
        days = int(args.get("days") or 7)
        date_from = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
        sales = wb.get_sales(date_from=date_from, flag=0)
        # Агрегируем по SKU
        agg: dict[str, dict] = {}
        for s in sales or []:
            sku = s.get("supplierArticle") or "?"
            rec = agg.setdefault(str(sku), {"orders": 0, "revenue": 0.0})
            rec["orders"] += 1
            rec["revenue"] += s.get("finishedPrice") or s.get("priceWithDisc") or s.get("totalPrice") or 0
        top = sorted(agg.items(), key=lambda x: x[1]["orders"], reverse=True)[:30]
        return {
            "period_days": days,
            "total_orders": sum(r["orders"] for _, r in agg.items()),
            "total_revenue": sum(r["revenue"] for _, r in agg.items()),
            "top_sku": [{"sku": k, **v} for k, v in top],
        }

    if name == "wb_unanswered_feedbacks":
        take = int(args.get("take") or 50)
        data = wb.get_feedbacks(is_answered=False, take=take, skip=0)
        # Достаём только нужное
        items = []
        for f in (data.get("data", {}) or {}).get("feedbacks", []) or []:
            items.append({
                "id": f.get("id"),
                "rating": f.get("productValuation"),
                "text": (f.get("text") or "")[:500],
                "pros": (f.get("pros") or "")[:200],
                "cons": (f.get("cons") or "")[:200],
                "sku": f.get("productDetails", {}).get("nmId"),
                "supplier_article": f.get("productDetails", {}).get("supplierArticle"),
                "created_date": f.get("createdDate"),
            })
        return {"count": len(items), "feedbacks": items}

    if name == "list_uploaded_files":
        files = []
        for p in UPLOADS_DIR.iterdir() if UPLOADS_DIR.exists() else []:
            if p.is_file():
                files.append({"name": p.name, "size_kb": round(p.stat().st_size / 1024, 1)})
        return {"files": files}

    if name == "read_uploaded_file":
        return _read_uploaded_file(args)

    return {"error": f"неизвестный инструмент: {name}"}


def _read_uploaded_file(args: dict) -> dict:
    """Парсит Excel/CSV. Возвращает headers, sample, numeric_summary."""
    filename = (args.get("filename") or "").strip()
    if not filename:
        return {"error": "filename не задан"}

    path = UPLOADS_DIR / filename
    if not path.exists():
        return {"error": f"файл {filename} не найден в uploads/"}

    sheet = args.get("sheet")
    max_rows = int(args.get("max_rows") or 200)

    try:
        import pandas as pd

        suffix = path.suffix.lower()
        if suffix in (".xlsx", ".xls", ".xlsm"):
            df = pd.read_excel(path, sheet_name=sheet) if sheet else pd.read_excel(path)
            if isinstance(df, dict):
                # sheet_name=None → dict of DataFrames; берём первый
                first_key = next(iter(df))
                df = df[first_key]
        elif suffix == ".csv":
            try:
                df = pd.read_csv(path, sep=None, engine="python")
            except Exception:
                df = pd.read_csv(path, sep=";")
        else:
            return {"error": f"поддерживаются только .xlsx/.xls/.csv, у тебя {suffix}"}

        df = df.head(max_rows)

        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        numeric_summary = {}
        for col in numeric_cols:
            try:
                numeric_summary[col] = {
                    "sum": float(df[col].sum()),
                    "mean": float(df[col].mean()),
                    "min": float(df[col].min()),
                    "max": float(df[col].max()),
                }
            except Exception:
                pass

        return {
            "filename": filename,
            "rows_returned": len(df),
            "headers": list(df.columns.astype(str)),
            "sample": df.fillna("").astype(str).head(50).to_dict(orient="records"),
            "numeric_summary": numeric_summary,
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
