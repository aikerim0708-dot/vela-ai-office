"""
Генератор отчётов VELA — авто-Vela Daily / Weekly / Monthly.

Идея: каждое утро в 7:00 cron на VDS вызывает generate_daily(yesterday) →
команда агентов через orchestrate_goal собирает структурированный отчёт →
сохраняется в data/reports/{date}-daily.md + .json.

Триггеры:
- daily — каждый день 07:00 за прошедший день
- weekly — воскресенье 21:00 за неделю
- monthly — последний день месяца 23:00 за месяц

Использование:
    from reports import generate_daily, generate_weekly, generate_monthly

    md, meta = generate_daily(date="2026-05-28")
    # → data/reports/2026-05-28-daily.md
    # → data/reports/2026-05-28-daily.json (метаданные)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date as date_cls, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Папка для хранения отчётов
DATA_DIR = Path(__file__).parent.parent / "data" / "reports"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ────────── Утилиты дат ──────────
def yesterday_iso() -> str:
    """Вчерашняя дата в ISO формате (YYYY-MM-DD)."""
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def week_id_for(d: date_cls) -> str:
    """ISO-неделя: 2026-W22 формат."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ────────── Загрузка контекстных файлов агентов ──────────
def load_agent_context(agent_slug: str) -> str:
    """Собирает все .md файлы из docs/<agent>-context/ в один блок."""
    project_root = Path(__file__).parent.parent
    ctx_dir = project_root / "docs" / f"{agent_slug}-context"
    if not ctx_dir.exists():
        return ""
    chunks: List[str] = []
    for f in sorted(ctx_dir.glob("*.md")):
        if f.name == "README.md":
            continue
        try:
            chunks.append(f"## Файл: {f.name}\n\n{f.read_text(encoding='utf-8')}")
        except Exception as e:
            log.warning("ошибка чтения %s: %s", f, e)
    return "\n\n---\n\n".join(chunks)


# ────────── Сбор данных WB для отчёта ──────────
def collect_wb_data_for_daily(target_date: str) -> Dict[str, Any]:
    """Собирает все нужные данные WB API за целевой день для daily report.

    Возвращает структурированный dict который потом передаётся агентам как
    контекст. Если какой-то источник недоступен — фиксирует это в результате
    но не падает.
    """
    from wb_client import WBClient, summarize_campaign_fullstats

    wb = WBClient()
    data: Dict[str, Any] = {
        "target_date": target_date,
        "errors": [],
    }

    # 1. Кампании fullstats (главное для Лео)
    try:
        stats_raw = wb.get_campaign_fullstats(
            campaign_ids=[29230612, 32284868],
            date_from=target_date,
            date_to=target_date,
        )
        data["campaigns_summary"] = summarize_campaign_fullstats(stats_raw)
        data["campaigns_raw"] = stats_raw
    except Exception as e:
        data["errors"].append(f"campaigns fullstats: {e}")
        data["campaigns_summary"] = []

    # 2. Продажи за вчера (для Зары)
    try:
        data["sales"] = wb.get_sales(date_from=target_date, flag=1)
    except Exception as e:
        data["errors"].append(f"sales: {e}")
        data["sales"] = []

    # 3. Заказы за вчера (для Анны)
    try:
        data["orders"] = wb.get_orders(date_from=target_date, flag=1)
    except Exception as e:
        data["errors"].append(f"orders: {e}")
        data["orders"] = []

    # 4. Остатки сегодня (для Анны)
    try:
        data["stocks"] = wb.get_stocks()
    except Exception as e:
        data["errors"].append(f"stocks: {e}")
        data["stocks"] = []

    # 5. Отзывы (для Евы)
    try:
        data["feedbacks"] = wb.get_feedbacks(is_answered=False, take=20, skip=0)
    except Exception as e:
        data["errors"].append(f"feedbacks: {e}")
        data["feedbacks"] = {}

    return data


def format_wb_data_for_prompt(data: Dict[str, Any]) -> str:
    """Превращает собранные WB данные в текст для system_prompt агентов."""
    parts = [f"# WB-данные за {data['target_date']}\n"]

    # Кампании
    parts.append("## Кампании (fullstats)\n")
    for camp in data.get("campaigns_summary", []) or []:
        cid = camp.get("campaign_id")
        name = "Бритва" if cid == 29230612 else "Ресницы" if cid == 32284868 else f"ID {cid}"
        parts.append(
            f"### {name} (id={cid})\n"
            f"- Показы: {camp.get('views', 0):,}\n"
            f"- Клики: {camp.get('clicks', 0):,}\n"
            f"- Заказы РК: {camp.get('orders', 0)}\n"
            f"- CTR: {camp.get('ctr', 0)}%\n"
            f"- CR: {camp.get('cr', 0)}%\n"
            f"- Затраты РК: {camp.get('cost', 0):,.0f} ₽\n"
            f"- Выручка РК: {camp.get('revenue_ad', 0):,.0f} ₽\n"
            f"- ДРР: {camp.get('drr', 0)}%\n"
        )
        # Топ кластеры
        clusters = (camp.get("clusters_top") or [])[:8]
        if clusters:
            parts.append("\n**Топ кластеров:**\n")
            for c in clusters:
                parts.append(
                    f"- {c.get('name', '?')}: CTR {c.get('ctr', 0)}%, "
                    f"CPO {c.get('cost', 0) / max(c.get('orders', 1), 1):.0f}₽, "
                    f"ДРР {c.get('drr', 0)}%, "
                    f"RPM {c.get('revenue_ad', 0) / max(c.get('views', 1), 1) * 1000:.0f}₽\n"
                )
        parts.append("\n")

    # Продажи
    sales = data.get("sales", [])
    if sales:
        parts.append(f"## Продажи за {data['target_date']}\n")
        parts.append(f"- Всего продаж: {len(sales)}\n")
        total_revenue = sum(s.get("finishedPrice", 0) for s in sales)
        parts.append(f"- Выручка: {total_revenue:,.0f} ₽\n\n")

    # Заказы
    orders = data.get("orders", [])
    if orders:
        parts.append(f"## Заказы за {data['target_date']}\n")
        parts.append(f"- Всего заказов: {len(orders)}\n\n")

    # Остатки
    stocks = data.get("stocks", [])
    if stocks:
        parts.append("## Остатки сейчас\n")
        total_qty = sum(s.get("quantity", 0) for s in stocks)
        parts.append(f"- Общий остаток: {total_qty:,} шт (по {len(stocks)} строкам)\n\n")

    # Ошибки
    errors = data.get("errors", [])
    if errors:
        parts.append("## ⚠️ Ошибки сбора данных\n")
        for err in errors:
            parts.append(f"- {err}\n")
        parts.append("\n")

    return "".join(parts)


# ────────── Генерация daily через агентов ──────────
def generate_daily(target_date: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """Генерирует Vela Daily за указанную дату (по умолчанию — вчера).

    Возвращает (markdown_text, metadata_dict).
    Сохраняет:
        data/reports/{date}-daily.md
        data/reports/{date}-daily.json
    """
    from agents import ClaudeAgentProvider, VELA_AGENTS  # type: ignore

    if not target_date:
        target_date = yesterday_iso()

    log.info("Генерация Vela Daily за %s", target_date)

    # 1. Собираем WB данные
    wb_data = collect_wb_data_for_daily(target_date)
    wb_block = format_wb_data_for_prompt(wb_data)

    # 2. Контексты агентов (read once для скорости)
    leo_ctx = load_agent_context("leo")
    anna_ctx = load_agent_context("anna")
    zara_ctx = load_agent_context("zara")
    eva_ctx = load_agent_context("eva")
    max_ctx = load_agent_context("max")

    # 3. Запускаем оркестратор через Макса
    provider = ClaudeAgentProvider()
    if not provider._available():  # type: ignore[attr-defined]
        # Если Claude API недоступен — возвращаем фолбек на сыром WB-блоке
        md = (
            f"# 🧠 VELA Daily · {target_date}\n\n"
            f"⚠️ Claude API недоступен. Это сырой WB-отчёт.\n\n"
            f"{wb_block}"
        )
        return md, {"date": target_date, "fallback": True}

    goal = (
        f"Сгенерировать Vela Daily за {target_date} в формате как в "
        f"docs/reports_architecture.md. Лео делает секцию по РК (по зонам, "
        f"кластерам, воронка CTR), Анна — остатки и поставки, Зара — финансы "
        f"и юнит-экономика, Ева — карточки и отзывы. Макс собирает итог "
        f"и формулирует TL;DR + рекомендации на завтра."
    )

    # Brain контекст = WB-данные + контексты всех агентов
    brain_context = (
        f"{wb_block}\n\n"
        f"# Контекст Лео\n{leo_ctx}\n\n"
        f"# Контекст Анны\n{anna_ctx}\n\n"
        f"# Контекст Зары\n{zara_ctx}\n\n"
        f"# Контекст Евы\n{eva_ctx}\n\n"
        f"# Контекст Макса\n{max_ctx}\n"
    )

    result = provider.orchestrate_goal(goal, brain_context=brain_context)

    # 4. Финальный markdown
    md_parts = [
        f"# 🧠 VELA Daily · {target_date}\n",
        f"_Автоматический отчёт. Сгенерирован {datetime.now(timezone.utc).isoformat()}._\n\n",
        "## 📋 Свод (Макс)\n\n",
        result.get("final_summary", "—"),
        "\n\n---\n\n## Разбор по агентам\n\n",
    ]

    for r in result.get("agent_results", []) or []:
        agent_emoji = {
            "leo": "🦁",
            "anna": "📦",
            "zara": "💰",
            "eva": "🎨",
            "max": "👨‍💼",
        }.get(r.get("agent", ""), "👤")
        md_parts.append(
            f"### {agent_emoji} {r.get('agent', 'agent').title()}\n\n"
            f"_Задача:_ {r.get('task', '')}\n\n"
            f"{r.get('output', '')}\n\n---\n\n"
        )

    md_parts.append("\n## 🔬 Сырые WB-данные\n\n<details><summary>Развернуть</summary>\n\n")
    md_parts.append(wb_block)
    md_parts.append("\n</details>\n")

    md = "".join(md_parts)

    # 5. Сохраняем
    md_path = DATA_DIR / f"{target_date}-daily.md"
    md_path.write_text(md, encoding="utf-8")

    meta = {
        "type": "daily",
        "date": target_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agents": [r.get("agent") for r in result.get("agent_results", []) or []],
        "wb_errors": wb_data.get("errors", []),
        "summary_first_500": result.get("final_summary", "")[:500],
    }
    json_path = DATA_DIR / f"{target_date}-daily.json"
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("Сохранён отчёт: %s", md_path)
    return md, meta


# ────────── Финансовая агрегация (для weekly/monthly) ──────────

# Юнит-экономика VELA из docs/zara-context/cost-structure.md
UNIT_ECONOMICS = {
    "razor": {
        "name": "Бритва (роз + фиол)",
        "price_rub": 510,
        "cogs_rub": 124,            # себестоимость
        "logistics_rub": 66,         # логистика с учётом 95% выкупа
        "retentions_pct": 0.32,      # комиссия + конструктор + налог УСН
        "profit_before_ads_rub": 156.8,
        "campaign_id": 29230612,
    },
    "lashes": {
        "name": "Ресницы",
        "price_rub": 550,
        "cogs_rub": 183,
        "logistics_rub": 66,
        "retentions_pct": 0.32,
        "profit_before_ads_rub": 125,
        "campaign_id": 32284868,
    },
}


def collect_period_data(date_from: str, date_to: str) -> Dict[str, Any]:
    """Собирает финансовые данные за период (sales + кампании + остатки)."""
    from wb_client import WBClient, summarize_campaign_fullstats

    wb = WBClient()
    data: Dict[str, Any] = {
        "date_from": date_from,
        "date_to": date_to,
        "errors": [],
    }

    # Продажи (выкупы)
    try:
        data["sales"] = wb.get_sales(date_from=date_from, flag=0) or []
    except Exception as e:
        data["errors"].append(f"sales: {e}")
        data["sales"] = []

    # Заказы
    try:
        data["orders"] = wb.get_orders(date_from=date_from, flag=0) or []
    except Exception as e:
        data["errors"].append(f"orders: {e}")
        data["orders"] = []

    # Кампании fullstats за период
    try:
        stats = wb.get_campaign_fullstats(
            campaign_ids=[29230612, 32284868],
            date_from=date_from,
            date_to=date_to,
        )
        data["campaigns"] = summarize_campaign_fullstats(stats)
    except Exception as e:
        data["errors"].append(f"campaigns: {e}")
        data["campaigns"] = []

    return data


def compute_pl_summary(period_data: Dict[str, Any]) -> Dict[str, Any]:
    """Считает P&L агрегированно за период."""
    sales = period_data.get("sales", [])
    orders = period_data.get("orders", [])
    campaigns = period_data.get("campaigns", [])

    total_sales_count = len(sales)
    total_orders_count = len(orders)
    total_revenue_rub = sum(s.get("finishedPrice", 0) for s in sales)

    # Удержания: 32% постоянных + 19% переменных (логистика+хранение) — оценка
    retentions_rub = total_revenue_rub * 0.32
    logistics_rub = total_revenue_rub * 0.19  # средняя по маю

    # Затраты на рекламу
    ads_total_rub = sum(c.get("cost", 0) for c in campaigns)

    # Себестоимость (взвешенно по двум товарам — приблизительно)
    # Точную разбивку получим когда добавим nmId маппинг
    avg_cogs = 130  # ₽/шт средняя
    cogs_rub = total_sales_count * avg_cogs

    net_profit_rub = (
        total_revenue_rub
        - retentions_rub
        - logistics_rub
        - ads_total_rub
        - cogs_rub
    )

    return {
        "sales_count": total_sales_count,
        "orders_count": total_orders_count,
        "revenue_rub": total_revenue_rub,
        "retentions_rub": retentions_rub,
        "logistics_rub": logistics_rub,
        "ads_rub": ads_total_rub,
        "cogs_rub": cogs_rub,
        "net_profit_rub": net_profit_rub,
        "net_margin_pct": (net_profit_rub / total_revenue_rub * 100) if total_revenue_rub else 0,
    }


# ────────── Weekly ──────────
def generate_weekly(week_end_date: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """Недельный отчёт. По умолчанию — за прошедшую неделю (заканчивающуюся в воскресенье)."""
    if not week_end_date:
        today = datetime.now(timezone.utc).date()
        days_since_sunday = (today.weekday() + 1) % 7
        sunday = today - timedelta(days=days_since_sunday or 7)
        week_end_date = sunday.isoformat()

    week_end = date_cls.fromisoformat(week_end_date)
    week_start = week_end - timedelta(days=6)
    week_id = week_id_for(week_end)

    log.info("Генерация weekly %s — %s (%s)", week_start, week_end, week_id)

    period_data = collect_period_data(week_start.isoformat(), week_end.isoformat())
    pl = compute_pl_summary(period_data)

    # Делегируем Заре через агентов
    md_body = _try_orchestrate_finance(
        period_label=f"неделя {week_start} — {week_end} ({week_id})",
        period_data=period_data,
        pl=pl,
        kind="weekly",
    )

    md = (
        f"# 📅 VELA Weekly · {week_id}\n\n"
        f"_Неделя: {week_start} — {week_end}. Сгенерирован {datetime.now(timezone.utc).isoformat()}._\n\n"
        f"## Сводный P&L\n\n"
        f"| Метрика | Значение |\n|---|---|\n"
        f"| Продано (выкуп) | {pl['sales_count']} шт |\n"
        f"| Заказов | {pl['orders_count']} шт |\n"
        f"| Выручка | {pl['revenue_rub']:,.0f} ₽ |\n"
        f"| Удержания ВБ (~32%) | {pl['retentions_rub']:,.0f} ₽ |\n"
        f"| Логистика + хранение (~19%) | {pl['logistics_rub']:,.0f} ₽ |\n"
        f"| Реклама | {pl['ads_rub']:,.0f} ₽ |\n"
        f"| Себестоимость | {pl['cogs_rub']:,.0f} ₽ |\n"
        f"| **Чистая прибыль** | **{pl['net_profit_rub']:,.0f} ₽** ({pl['net_margin_pct']:.1f}%) |\n\n"
        f"---\n\n"
        f"{md_body}\n\n"
        f"---\n\n"
        f"_Реальные удержания смотри через `reportDetailByPeriod` на следующей неделе._\n"
    )

    meta = {
        "type": "weekly",
        "week_id": week_id,
        "week_end": week_end_date,
        "week_start": week_start.isoformat(),
        "pl": pl,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    (DATA_DIR / f"{week_id}-weekly.md").write_text(md, encoding="utf-8")
    (DATA_DIR / f"{week_id}-weekly.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return md, meta


# ────────── Monthly ──────────
def generate_monthly(month: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """Месячный финансовый отчёт. month формат: 'YYYY-MM'."""
    if not month:
        today = datetime.now(timezone.utc).date()
        first_of_month = today.replace(day=1)
        prev = first_of_month - timedelta(days=1)
        month = f"{prev.year}-{prev.month:02d}"

    y, m = month.split("-")
    y, m = int(y), int(m)
    month_start = date_cls(y, m, 1)
    if m == 12:
        month_end = date_cls(y + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date_cls(y, m + 1, 1) - timedelta(days=1)

    log.info("Генерация monthly за %s (%s — %s)", month, month_start, month_end)

    period_data = collect_period_data(month_start.isoformat(), month_end.isoformat())
    pl = compute_pl_summary(period_data)

    md_body = _try_orchestrate_finance(
        period_label=f"месяц {month} ({month_start} — {month_end})",
        period_data=period_data,
        pl=pl,
        kind="monthly",
    )

    months_ru = ["", "январь", "февраль", "март", "апрель", "май", "июнь",
                 "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    month_label = f"{months_ru[m]} {y}"

    md = (
        f"# 💰 VELA Finance · {month_label}\n\n"
        f"_Полный финансовый разбор {month_start} — {month_end}._\n\n"
        f"## 📊 Сводный P&L\n\n"
        f"| Статья | Сумма ₽ | % от выручки |\n|---|---|---|\n"
        f"| Выручка | {pl['revenue_rub']:,.0f} | 100% |\n"
        f"| Удержания ВБ | {pl['retentions_rub']:,.0f} | {pl['retentions_rub']/max(pl['revenue_rub'],1)*100:.1f}% |\n"
        f"| Логистика + хранение | {pl['logistics_rub']:,.0f} | {pl['logistics_rub']/max(pl['revenue_rub'],1)*100:.1f}% |\n"
        f"| Реклама | {pl['ads_rub']:,.0f} | {pl['ads_rub']/max(pl['revenue_rub'],1)*100:.1f}% |\n"
        f"| Себестоимость | {pl['cogs_rub']:,.0f} | {pl['cogs_rub']/max(pl['revenue_rub'],1)*100:.1f}% |\n"
        f"| **Чистая прибыль** | **{pl['net_profit_rub']:,.0f}** | **{pl['net_margin_pct']:.1f}%** |\n\n"
        f"Продано: {pl['sales_count']} шт. Заказов: {pl['orders_count']} шт.\n\n"
        f"---\n\n"
        f"## 📦 Юнит-экономика\n\n"
        f"### Бритва (роз + фиол)\n"
        f"- Цена WB: 510 ₽ / 3 162 ₸\n"
        f"- Себестоимость: 124 ₽ / 767 ₸\n"
        f"- Прибыль до рекламы: **+156.8 ₽ / +972 ₸**\n"
        f"- Маржинальность: 30.7%\n\n"
        f"### Ресницы\n"
        f"- Цена WB: 550 ₽ / 3 410 ₸\n"
        f"- Себестоимость: 183 ₽ / 1 136 ₸\n"
        f"- Прибыль до рекламы: **+125 ₽ / +775 ₸**\n"
        f"- Маржинальность: 22.7%\n\n"
        f"---\n\n"
        f"{md_body}\n"
    )

    meta = {
        "type": "monthly",
        "month": month,
        "month_label": month_label,
        "pl": pl,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    (DATA_DIR / f"{month}-finance.md").write_text(md, encoding="utf-8")
    (DATA_DIR / f"{month}-finance.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return md, meta


def _try_orchestrate_finance(
    period_label: str,
    period_data: Dict[str, Any],
    pl: Dict[str, Any],
    kind: str,
) -> str:
    """Пробует прогнать через агентов Зары + Макса. При ошибке возвращает базовый текст."""
    try:
        from agents import ClaudeAgentProvider
        provider = ClaudeAgentProvider()
        if not provider._available():  # type: ignore[attr-defined]
            return "_Claude API недоступен — расширенная аналитика пропущена._"
    except Exception:
        return "_Агенты недоступны — расширенная аналитика пропущена._"

    zara_ctx = load_agent_context("zara")
    pl_text = (
        f"# P&L агрегаты за {period_label}\n\n"
        f"- Выручка: {pl['revenue_rub']:,.0f} ₽\n"
        f"- Удержания: {pl['retentions_rub']:,.0f} ₽\n"
        f"- Логистика: {pl['logistics_rub']:,.0f} ₽\n"
        f"- Реклама: {pl['ads_rub']:,.0f} ₽\n"
        f"- Себестоимость: {pl['cogs_rub']:,.0f} ₽\n"
        f"- Чистая прибыль: {pl['net_profit_rub']:,.0f} ₽ ({pl['net_margin_pct']:.1f}%)\n"
        f"- Продажи: {pl['sales_count']} шт\n"
    )

    goal = (
        f"Сделать {kind} финансовый разбор VELA за {period_label}. "
        f"Зара: оценить P&L по разделам, найти аномалии, дать рекомендации. "
        f"Макс: сводный TL;DR с приоритетами."
    )
    brain_context = f"{pl_text}\n\n# Контекст Зары\n{zara_ctx}\n"

    try:
        result = provider.orchestrate_goal(goal, brain_context=brain_context)
        parts = ["## Анализ агентов\n"]
        for r in result.get("agent_results", []) or []:
            agent = r.get("agent", "")
            emoji = {"zara": "💰", "max": "👨‍💼", "leo": "🦁", "anna": "📦", "eva": "🎨"}.get(agent, "👤")
            parts.append(f"\n### {emoji} {agent.title()}\n\n{r.get('output', '')}\n")
        parts.append("\n## 📋 Свод Макса\n\n" + result.get("final_summary", "—"))
        return "\n".join(parts)
    except Exception as e:
        log.warning("orchestrate_goal failed: %s", e)
        return f"_Не удалось вызвать агентов: {e}_"


# ────────── Список / чтение существующих отчётов ──────────
def list_reports() -> List[Dict[str, Any]]:
    """Возвращает список всех отчётов с метаданными."""
    reports: List[Dict[str, Any]] = []
    for json_file in sorted(DATA_DIR.glob("*.json")):
        try:
            meta = json.loads(json_file.read_text(encoding="utf-8"))
            md_path = json_file.with_suffix(".md")
            meta["md_path"] = str(md_path)
            meta["filename"] = md_path.name
            reports.append(meta)
        except Exception as e:
            log.warning("ошибка чтения %s: %s", json_file, e)
    return reports


def read_report(filename: str) -> Optional[str]:
    """Читает отчёт по имени файла (с .md или без)."""
    if not filename.endswith(".md"):
        filename += ".md"
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
