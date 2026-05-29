"""
VELA AI Office — команда из 5 агентов-персонажей + Brain VELA.

Архитектура:
- Макс (Chief) — координирует, эскалирует, не делает аналитику сам
- Лео (Perf Marketing) — реклама, ставки, кластеры, цены
- Анна (Supply Ops) — поставки, склады, OOS, логистика
- Зара (CFO) — юнит-эка, P&L, sanity-check
- Ева (Marketing) — карточки, контент, A/B, отзывы

Все агенты пишут в Brain VELA (общая SQLite-память) и могут передавать
задачу друг другу (handoff).

MockAgentProvider — заглушки.
ClaudeAgentProvider — реальный Claude API + загрузка скиллов VELA.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Protocol
from datetime import datetime

from brief_format import BRIEF_INSTRUCTION


# ---------------------------------------------------------------------------
# КАТАЛОГ КОМАНДЫ
# ---------------------------------------------------------------------------

VELA_AGENTS = [
    {
        "slug": "max",
        "name": "Макс",
        "role": "Chief / Координатор офиса",
        "title": "Руководитель команды VELA",
        "avatar_emoji": "👨‍💼",
        "color": "#4f46e5",
        "primary_metric": "≥ 80% дней команда в нормах, эскалации <2 в неделю",
        "schedule": "Стендап 09:30 · Недельный отчёт пн 11:00",
        "responsibilities": [
            "Контроль команды: SLA по времени, качеству, ошибкам",
            "Утренний стендап в общем чате",
            "Эскалация Айкерим только когда нужно",
            "Разрешение конфликтов между агентами (Лео хочет — Зара говорит нельзя)",
            "Недельный отчёт офиса по KPI всех агентов",
        ],
        "stop_signals": [
            "Любой агент не сработал 2 дня подряд → пинг Айкерим",
            "Несколько агентов дают противоречивые рекомендации → стоп исполнение, зов Айкерим",
        ],
        "skill": "vela-supervisor",
        "templates": [
            {
                "title": "Утренний стендап",
                "prompt": "Собери утренний стендап команды VELA на сегодня. Проверь кто из агентов сработал, что в очереди на approve, какие 🔴 эскалации. Формат: для каждого агента — статус, ключевая цифра, флаги.",
            },
            {
                "title": "Недельный отчёт офиса",
                "prompt": "Сделай недельный отчёт офиса VELA. Для каждого агента — попал ли в свою метрику. Список применённых решений vs черновых. Гипотезы недели и их статус. Что предлагаешь на следующую неделю.",
            },
        ],
    },
    {
        "slug": "leo",
        "name": "Лео",
        "role": "Performance Marketing Lead",
        "title": "Реклама, ставки, кластеры",
        "avatar_emoji": "🦁",
        "color": "#f59e0b",
        "primary_metric": "ДРР по 29230612 и 32284868 ↓ ≥ 15% за 4 недели",
        "schedule": "09:30 утро · 14:00 обед · 19:00 вечер",
        "responsibilities": [
            "Реклама: кампании 29230612 (бритвы), 32284868 (ресницы)",
            "Корректировки ставок по кластерам (черновики, не применяет)",
            "Мониторинг CTR/CR/EPC по кластерам — нормы по бритвам/ресницам",
            "Решения по выключению гниющих кластеров",
            "Цены — sanity-check у Зары перед изменением",
        ],
        "workflow": [
            "09:30 — разбор вчерашнего ДРР, черновик корректировок",
            "14:00 — обед-чек: как сыграли утренние правки",
            "19:00 — вечер-чек: дневные итоги, что выключить на ночь",
        ],
        "stop_signals": [
            "Ставка ведёт SKU в минус → запрос Заре, без её ОК — стоп",
            "ДРР растёт 3 дня после правок → стоп черновиков, зов Макса",
        ],
        "handoffs": {
            "to_zara": "Перед изменением ставки/цены — sanity-check у Зары",
            "to_eva": "Если кластер просел по контентной причине (CTR упал, CR не страдает) — отдать Еве",
        },
        "skill": "vela-bid-manager",
        "templates": [
            {
                "title": "Утренний разбор рекламы",
                "prompt": "Разбери вчерашний день по рекламе VELA. По обеим кампаниям: расход, выручка-AD, ДРР, CTR/CR/EPC по кластерам. Найди где просели и предложи черновик корректировок ставок (было → станет, причина, ожидаемый эффект). Цифры не выдумывай — если данных нет, пиши [нет данных].",
            },
            {
                "title": "Midday чек — как сыграли утренние правки",
                "prompt": "Проверь как отработали утренние правки ставок к 14:00. По каждому изменённому кластеру: текущий ДРР vs цель, динамика CTR/CR. Если что-то идёт не так — предлагай новые правки.",
            },
            {
                "title": "Вечерний чек — что выключить на ночь",
                "prompt": "Дневной итог по рекламе VELA. Какие кластеры дают плохой ДРР под вечер (низкая конверсия, дорогой трафик). Предложи что выключить на ночь чтобы не сливать бюджет.",
            },
        ],
    },
    {
        "slug": "anna",
        "name": "Анна",
        "role": "Supply Operations Lead",
        "title": "Поставки, склады, OOS",
        "avatar_emoji": "📦",
        "color": "#10b981",
        "primary_metric": "OOS-дней по топ-10 SKU за квартал минимум",
        "schedule": "09:00 утренний снапшот складов · понедельник 11:00 план поставок на неделю",
        "responsibilities": [
            "Остатки FBO/FBS — мониторинг по топ-SKU",
            "Распределение остатков по складам (Коледино, Электросталь, Казань, СПб, Краснодар)",
            "Прогноз velocity и DOS (days of stock) по топ-10",
            "Логистика Китай→РФ: lead-time, риски, задержки, MOQ",
            "Черновики поставок (что, куда, сколько, до какой даты)",
            "Анализ складов конкурентов (откуда они грузят)",
        ],
        "stop_signals": [
            "DOS ≤ lead-time → 🔴 Айкерим немедленно",
            "Сезонный коэффициент не учтён (школа, новый год) → требует ручной корректировки",
        ],
        "handoffs": {
            "to_zara": "Перед заказом поставщику — проверка экономики поставки",
            "to_leo": "Если SKU в OOS-риске — Лео должен снизить или выключить рекламу",
        },
        "skill": "vela-stock-forecast",
        "templates": [
            {
                "title": "Утренний снапшот складов",
                "prompt": "Сделай снапшот остатков VELA на сегодня. По топ-10 SKU: остаток FBO + FBS, velocity 7/14/30, DOS, lead-time, риск OOS. 🔴 где DOS ≤ lead-time. 🟡 где DOS ≤ 1.5×lead-time.",
            },
            {
                "title": "План поставок на неделю",
                "prompt": "Составь план поставок VELA на следующую неделю. По каждому SKU в риск-зоне: сколько везти из Китая, до какого числа, через какую логистику. Учти сезонность и MOQ поставщика.",
            },
            {
                "title": "Распределение остатков по складам",
                "prompt": "По топ-SKU посмотри географию продаж и предложи перераспределение по складам WB. Где не хватает — туда отправить. Где избыток — оттуда забрать.",
            },
        ],
    },
    {
        "slug": "zara",
        "name": "Зара",
        "role": "CFO / Финансовый аналитик",
        "title": "Юнит-эка, P&L, sanity-check",
        "avatar_emoji": "💰",
        "color": "#8b5cf6",
        "primary_metric": "≥ 90% решений прошли sanity-check, прибыль ₽/шт защищена",
        "schedule": "09:25 sanity-check черновиков Лео · 20:00 дневной P&L · понедельник 12:00 weekly P&L",
        "responsibilities": [
            "Юнит-экономика всех SKU: поставка → логистика → хранение → реклама → комиссия WB → налог → прибыль ₽/шт",
            "Sanity-check решений Лео (ставки/цены) и Анны (поставки)",
            "Daily/Weekly/Monthly P&L",
            "CAC по кампаниям, ROI по кластерам",
            "Контроль расхождения формула vs факт",
        ],
        "stop_signals": [
            "Решение даёт прибыль ≤ 0 → жёсткий блок до approve Айкерим с фразой «понимаю что в минус»",
            "Расхождение формула/факт > 10% → стоп и калибровка",
        ],
        "handoffs": {
            "to_leo": "Если расход растёт быстрее выручки — алерт",
            "to_anna": "Если стоимость поставки выросла → пересчитать цену продажи с Айкерим",
        },
        "skill": "vela-unit-econ",
        "templates": [
            {
                "title": "Sanity-check решения",
                "prompt": "Проверь решение: [что меняем — цена/ставка/закуп]. Прогони через юнит-экономику. Покажи: было / станет / прибыль ₽/шт / вердикт 🟢🟡🔴 / что сделать чтобы стало 🟢.",
            },
            {
                "title": "Дневной P&L",
                "prompt": "Сделай P&L VELA за вчера. Выручка, расходы по статьям (СС, логистика, хранение, реклама, комиссия, налог), маржа, прибыль ₽. Сравни с базовой линией недели. Аномалии — флаги.",
            },
            {
                "title": "Недельный P&L и тренды",
                "prompt": "Недельный P&L VELA. По дням: выручка, прибыль, ДРР, CAC. Тренды по сравнению с прошлой неделей. Где маржа поплыла — почему.",
            },
        ],
    },
    {
        "slug": "eva",
        "name": "Ева",
        "role": "Marketing Lead",
        "title": "Карточки, контент, конкуренты",
        "avatar_emoji": "🎨",
        "color": "#ec4899",
        "primary_metric": "CR корзина→заказ по топ-SKU ↑ ≥ 10% за 6 недель",
        "schedule": "понедельник 10:00 — недельный обзор · по запросу — A/B и анализ",
        "responsibilities": [
            "Карточки SKU: фото, инфографика, заголовки, описания, SEO",
            "Контентная воронка продаж по каждому топ-SKU",
            "Анализ конкурентов: что у топ-10 в каждом кластере",
            "A/B тесты гипотез — каждая с метрикой, сроком, критерием успеха",
            "Портрет покупателя по сегментам (бритвы для мужчин / ресницы для девушек)",
            "Тренды рынка маркетплейсов: что нового внедрять",
            "Триаж отзывов: классификация, черновики ответов, агрегация паттернов негатива",
        ],
        "stop_signals": [
            "Гипотеза без метрики/срока/критерия — не выпускает",
            "Юридическая угроза в отзыве — стоп, зовёт Айкерим",
        ],
        "handoffs": {
            "to_leo": "Если карточка готова, можно пушить рекламой — Лео разгоняет",
            "from_leo": "Если у Лео кластер просел по контенту — Ева аудит карточки",
        },
        "skill": "vela-card-marketing",
        "templates": [
            {
                "title": "Аудит карточки",
                "prompt": "Сделай аудит карточки [артикул SKU] по чек-листу: фото (1-й кадр захватывает?), инфографика (преимущества видны за 3 сек?), заголовок (SEO-ключи + триггер?), описание (закрывает возражения?), цена и преимущества vs конкуренты. Дай приоритизированный список изменений с ожидаемым эффектом на CR.",
            },
            {
                "title": "Анализ конкурентов в кластере",
                "prompt": "Возьми кластер [название] и проанализируй топ-10 карточек конкурентов. Что у них общего, что отличает, в чём наше преимущество, в чём слабость. Дай гипотезы для A/B на нашей карточке.",
            },
            {
                "title": "Триаж отзывов",
                "prompt": "Возьми последние 10 отзывов VELA. Классифицируй по типу (доставка/качество/упаковка/инструкция/другое) и звёздам. По 1-2★ предложи черновики ответов в нашем тоне. Агрегируй паттерны негатива — что чаще всего жалуются.",
            },
        ],
    },
]


def find_agent(slug: str) -> dict | None:
    for agent in VELA_AGENTS:
        if agent["slug"] == slug:
            return agent
    return None


# ---------------------------------------------------------------------------
# PROVIDER INTERFACE
# ---------------------------------------------------------------------------


class AgentProvider(Protocol):
    def list_agents(self) -> list[dict]: ...

    def get_agent(self, slug: str) -> dict | None: ...

    def run_task(self, agent_slug: str, prompt: str) -> dict: ...


# ---------------------------------------------------------------------------
# MOCK PROVIDER (заглушки для разработки)
# ---------------------------------------------------------------------------


class MockAgentProvider:
    def list_agents(self) -> list[dict]:
        return [
            {k: v for k, v in agent.items() if k != "templates"}
            for agent in VELA_AGENTS
        ]

    def get_agent(self, slug: str) -> dict | None:
        return find_agent(slug)

    def get_templates(self, slug: str) -> list[dict]:
        agent = find_agent(slug)
        return agent.get("templates", []) if agent else []

    def run_task(self, agent_slug: str, prompt: str) -> dict:
        agent = find_agent(agent_slug)
        if not agent:
            return {"status": "failed", "output": f"Агент {agent_slug} не найден"}

        return {
            "status": "succeeded",
            "agent": agent["name"],
            "skill": agent.get("skill"),
            "prompt": prompt,
            "output": f"[MOCK] {agent['name']} ({agent['role']}) принял задачу:\n\n«{prompt}»\n\nДля реального ответа нужны: данные WB + ANTHROPIC_API_KEY в .env + VELA_PROVIDER=claude",
            "is_mock": True,
            "completed_at": datetime.utcnow().isoformat() + "Z",
        }


# ---------------------------------------------------------------------------
# CLAUDE PROVIDER (реальные агенты через Claude API)
# ---------------------------------------------------------------------------

_SKILLS_DIR = Path(__file__).parent.parent / "skills"
_DOCS_DIR = Path(__file__).parent.parent / "docs"

# Маппинг агента → его контекстная папка docs/<agent>-context/
# Там лежат реальные цифры VELA (юнит-экономика, нормы ДРР, метрики).
_CONTEXT_DIRS = {
    "max": "max-context",
    "leo": "leo-context",
    "anna": "anna-context",
    "zara": "zara-context",
    "eva": "eva-context",
}

# Каждому агенту можно дать несколько скиллов — все загружаются как system prompt.
# Это позволяет Лео знать и про сбор данных (daily-report), и про здоровье кластеров,
# и про правила корректировки ставок (bid-manager).
_SKILL_PATHS = {
    "max":  [_SKILLS_DIR / "max-ceo" / "SKILL.md"],
    "leo":  [_SKILLS_DIR / "leo-performance" / "SKILL.md"],
    "anna": [_SKILLS_DIR / "anna-supply" / "SKILL.md"],
    "zara": [_SKILLS_DIR / "zara-cfo" / "SKILL.md"],
    "eva":  [_SKILLS_DIR / "eva-marketing" / "SKILL.md"],
}


def _load_agent_context_files(slug: str) -> str:
    """Собирает все .md (кроме README) из docs/<agent>-context/ — реальные цифры VELA."""
    ctx_name = _CONTEXT_DIRS.get(slug)
    if not ctx_name:
        return ""
    ctx_dir = _DOCS_DIR / ctx_name
    if not ctx_dir.exists():
        return ""
    chunks = []
    for f in sorted(ctx_dir.glob("*.md")):
        if f.name == "README.md":
            continue
        try:
            chunks.append(f"#### {f.name}\n\n{f.read_text(encoding='utf-8')}")
        except Exception:
            pass
    return "\n\n".join(chunks)


def _fallback_prompt(agent: dict, brain_summary: str = "") -> str:
    """Fallback системный промпт если SKILL.md ещё не написан."""
    workflow = "\n".join(f"- {x}" for x in agent.get("workflow", []))
    responsibilities = "\n".join(f"- {x}" for x in agent.get("responsibilities", []))
    stop_signals = "\n".join(f"- {x}" for x in agent.get("stop_signals", []))
    handoffs = agent.get("handoffs", {})
    handoffs_str = (
        "\n".join(f"- {who}: {what}" for who, what in handoffs.items())
        if handoffs
        else "—"
    )

    brain_block = ""
    if brain_summary:
        brain_block = f"\n\n## Brain VELA (общая память команды)\n{brain_summary}\n"

    return f"""Ты {agent['name']} — {agent['role']} в офисе VELA на Wildberries.

Бизнес VELA: бренд на WB, две основных категории — бритвы (кампания 29230612) и накладные ресницы (кампания 32284868). Владелец — Айкерим.

## Твоя зона ответственности
{responsibilities}

## Целевая метрика
{agent['primary_metric']}

## Расписание
{agent['schedule']}

{workflow}

## Стоп-краны
{stop_signals}

## Handoff другим агентам
{handoffs_str}

## Команда офиса
- 👨‍💼 Макс — Chief / Координатор
- 🦁 Лео — Performance Marketing Lead
- 📦 Анна — Supply Operations Lead
- 💰 Зара — CFO / Финансовый аналитик
- 🎨 Ева — Marketing Lead
{brain_block}

## Правила работы
1. **Цифры берутся из источника** (CSV, выгрузка, скрин). Если источника нет — пиши `[нет данных]`, не выдумывай.
2. **Каждая гипотеза = метрика + срок + критерий успеха + что делаем если не зашло**.
3. **Не действуй сам** — все решения сначала к Айкерим на approve.
4. **Если задача не двигает чистую прибыль VELA — скажи это первым**.
5. **Кратко, конкретно, с цифрами**. Без воды и общих фраз.
6. **Сезонность WB учитывай** (Q4, новый год, школа, чёрная пятница).

Если получаешь задачу не из своей зоны — предложи handoff подходящему агенту.
{BRIEF_INSTRUCTION}
"""


def _read_skill_file(path: Path) -> str:
    """Читает SKILL.md, убирает YAML-frontmatter."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2].strip()
    return text


def _load_skill_prompt(slug: str) -> str:
    agent = find_agent(slug)
    if not agent:
        return f"Ты агент {slug} офиса VELA."

    paths = _SKILL_PATHS.get(slug, [])
    # Совместимость: если один Path (не list) — превращаем в список
    if isinstance(paths, Path):
        paths = [paths]

    skill_chunks = []
    for path in paths:
        if path and path.exists():
            content = _read_skill_file(path)
            skill_chunks.append(f"### Скилл: {path.parent.name}\n\n{content}")

            # Если рядом со SKILL.md лежит PLAYBOOK.md — добавляем как ежедневный SOP
            playbook = path.parent / "PLAYBOOK.md"
            if playbook.exists():
                playbook_text = playbook.read_text(encoding="utf-8")
                # PLAYBOOK не имеет YAML-frontmatter, читаем как есть
                skill_chunks.append(
                    f"### Ежедневный playbook агента ({path.parent.name})\n\n"
                    f"Это ОБЯЗАТЕЛЬНЫЙ пошаговый протокол. Следуй ему когда выполняешь "
                    f"задачи входящие в утренний/обеденный/вечерний цикл.\n\n"
                    f"{playbook_text}"
                )

    team_context = _fallback_prompt(agent)

    # Контекстные файлы docs/<agent>-context/ — реальные цифры VELA
    ctx_files = _load_agent_context_files(slug)
    ctx_block = ""
    if ctx_files:
        ctx_block = (
            "\n\n---\n\n## База знаний агента (реальные данные VELA)\n\n"
            "Это твоя рабочая база: нормы, формулы, юнит-экономика, метрики. "
            "Опирайся на эти цифры, не выдумывай.\n\n"
            f"{ctx_files}"
        )

    if skill_chunks:
        skills_block = "\n\n---\n\n".join(skill_chunks)
        return f"{skills_block}\n\n---\n\n{team_context}{ctx_block}"

    # Скиллов нет — fallback + контекст
    return f"{team_context}{ctx_block}"


MAX_ORCHESTRATOR_INSTRUCTIONS = """

## Дополнительная роль — Орк­естратор команды (только для Макса)

Когда Айкерим ставит ЦЕЛЬ команде, ты:

1. Анализируешь — что именно она хочет получить.
2. Решаешь — каких агентов из команды нужно подключить и что каждому делать.
3. Отвечаешь СТРОГО в формате JSON между маркерами `<PLAN>` и `</PLAN>`:

<PLAN>
{
  "goal": "краткая формулировка цели Айкерим",
  "plan": "1-2 предложения о том как команда это решит",
  "delegations": [
    {"agent": "leo",  "task": "конкретный промпт для Лео — что именно сделать"},
    {"agent": "anna", "task": "конкретный промпт для Анны"},
    {"agent": "zara", "task": "конкретный промпт для Зары"},
    {"agent": "eva",  "task": "конкретный промпт для Евы"}
  ],
  "needs_data_from_aikerim": ["список того что должна приложить Айкерим: WB Seller CSV, экспорт кампании 29230612, остатки, отзывы — или пусто если не нужно"]
}
</PLAN>

Правила:
- Делегируй только тех агентов которые действительно нужны для цели. Не зови всех если запрос узкий.
- Каждая задача — конкретный промпт от первого лица («собери», «проверь», «дай черновик»).
- Если для цели нужны данные от Айкерим которых нет в её сообщении — обязательно перечисли в `needs_data_from_aikerim`.
- Не пиши ничего вне `<PLAN>...</PLAN>` блока в этом режиме.

Когда команда выполнит свои задачи, ты получишь их результаты и должен будешь собрать **финальный сводный отчёт** для Айкерим: ключевые цифры, флаги 🟢🟡🔴, рекомендации, что приоритетно approve.
"""

SUMMARY_INSTRUCTIONS = """
Команда выполнила свои задачи. Ниже их ответы. Собери итоговый отчёт для Айкерим в формате:

# 📋 Сводка команды VELA — <дата/контекст>

**🎯 Цель:** <что просила Айкерим>

**📊 Что собрали (короткие выжимки от каждого агента):**
- 🦁 Лео: <2-3 цифры/вывода>
- 📦 Анна: <2-3 цифры/вывода>
- 💰 Зара: <2-3 цифры/вывода>
- 🎨 Ева: <2-3 цифры/вывода>

(только тех агентов которые отвечали)

**🚨 Аномалии (требуют внимания):**
- 🔴 ...
- 🟡 ...

**✅ Готово к approve Айкерим:**
1. ...
2. ...

**❓ Что нужно от тебя:**
- Если нужно данные / решения — перечисли

**🧠 Записано в Brain VELA:**
- Новые гипотезы / события (если есть)

Будь краткой. Если в ответах агентов мусор/нет данных — честно скажи «данных нет», не выдумывай.
"""


class ClaudeAgentProvider:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5"):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self._skill_cache = {slug: _load_skill_prompt(slug) for slug in _SKILL_PATHS}
        # Для Макса добавляем режим оркестратора
        if "max" in self._skill_cache:
            self._skill_cache["max"] += MAX_ORCHESTRATOR_INSTRUCTIONS

    def list_agents(self) -> list[dict]:
        return [
            {k: v for k, v in agent.items() if k != "templates"}
            for agent in VELA_AGENTS
        ]

    def get_agent(self, slug: str) -> dict | None:
        return find_agent(slug)

    def get_templates(self, slug: str) -> list[dict]:
        agent = find_agent(slug)
        return agent.get("templates", []) if agent else []

    def run_task(self, agent_slug: str, prompt: str, brain_context: str = "",
                 history: Optional[list] = None) -> dict:
        agent = find_agent(agent_slug)
        if not agent:
            return {"status": "failed", "output": f"Агент {agent_slug} не найден"}

        system_prompt = self._skill_cache.get(agent_slug, _fallback_prompt(agent))
        if brain_context:
            system_prompt += f"\n\n## Текущее состояние Brain VELA\n{brain_context}\n"

        # ---- Tool use: даём агенту инструменты под его роль ----
        from wb_tools import get_tools_for_agent, dispatch_tool_call

        tools = get_tools_for_agent(agent_slug)
        if tools:
            system_prompt += (
                "\n\n## Доступ к WB API\n"
                "У тебя есть инструменты для запроса реальных данных Wildberries.\n"
                "ИСПОЛЬЗУЙ их вместо того чтобы писать «нет данных». Сначала вызови нужный инструмент, "
                "потом анализируй ответ. Кампании VELA: 29230612 (бритвы), 32284868 (ресницы).\n"
                "Если инструмент вернул ошибку токена — скажи Айкерим что нужно настроить WB_API_TOKEN.\n"
            )

        try:
            return self._run_with_tools(
                agent=agent,
                system_prompt=system_prompt,
                user_prompt=prompt,
                tools=tools,
                dispatch=dispatch_tool_call,
                history=history,
            )
        except Exception as e:
            return {
                "status": "failed",
                "agent": agent["name"],
                "prompt": prompt,
                "output": f"Ошибка Claude API: {type(e).__name__}: {e}",
                "is_mock": False,
                "completed_at": datetime.utcnow().isoformat() + "Z",
            }

    def _run_with_tools(
        self,
        *,
        agent: dict,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict],
        dispatch,
        max_iters: int = 6,
        history: Optional[list] = None,
    ) -> dict:
        """Цикл tool use Claude: модель вызывает инструменты пока сама не решит остановиться.

        Если tools пуст — обычный одноходовой вызов.
        history — предыдущие реплики диалога [{role, content}] для памяти (личка с Максом).
        """
        messages = []
        if history:
            # Anthropic требует чтобы первая реплика была от user — срезаем ведущие assistant
            h = list(history)
            while h and h[0].get("role") != "user":
                h.pop(0)
            messages.extend(h)
        messages.append({"role": "user", "content": user_prompt})
        tool_calls_log: list[dict] = []

        for _ in range(max_iters):
            kwargs = dict(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
            )
            if tools:
                kwargs["tools"] = tools

            msg = self.client.messages.create(**kwargs)

            # Если stop_reason != tool_use — модель ответила финально
            if msg.stop_reason != "tool_use":
                output_text = "\n".join(
                    block.text for block in msg.content if hasattr(block, "text")
                )
                return {
                    "status": "succeeded",
                    "agent": agent["name"],
                    "skill": agent.get("skill"),
                    "prompt": user_prompt,
                    "output": output_text,
                    "tool_calls": tool_calls_log,
                    "is_mock": False,
                    "model": self.model,
                    "completed_at": datetime.utcnow().isoformat() + "Z",
                }

            # Иначе — собираем tool_use блоки, выполняем, возвращаем как tool_result
            assistant_blocks = list(msg.content)
            messages.append({"role": "assistant", "content": assistant_blocks})

            tool_results = []
            for block in assistant_blocks:
                if getattr(block, "type", None) == "tool_use":
                    name = block.name
                    args = block.input or {}
                    try:
                        result = dispatch(name, args)
                        is_error = False
                    except Exception as ex:
                        result = {"error": f"{type(ex).__name__}: {ex}"}
                        is_error = True
                    tool_calls_log.append({
                        "name": name,
                        "args": args,
                        "ok": not is_error,
                    })
                    # Сериализуем результат для модели — JSON-строкой
                    import json as _json
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _json.dumps(result, ensure_ascii=False, default=str)[:30000],
                        "is_error": is_error,
                    })

            messages.append({"role": "user", "content": tool_results})

        # Превысили max_iters — возвращаем что есть
        return {
            "status": "failed",
            "agent": agent["name"],
            "prompt": user_prompt,
            "output": f"Превышен лимит итераций tool use ({max_iters}). Слишком много обращений к WB.",
            "tool_calls": tool_calls_log,
            "is_mock": False,
            "completed_at": datetime.utcnow().isoformat() + "Z",
        }


    def orchestrate_goal(self, goal: str, brain_context: str = "") -> dict:
        """Полный цикл: Макс планирует → агенты делают → Макс сводит.

        Возвращает {plan, delegations, agent_results, final_summary, total_tokens}.
        """
        import json
        import re
        from concurrent.futures import ThreadPoolExecutor

        # ---- 1. Макс получает цель и возвращает JSON-план ----
        plan_response = self.run_task("max", f"Айкерим ставит цель команде:\n\n{goal}", brain_context=brain_context)
        plan_text = plan_response.get("output", "")

        # Извлекаем JSON из <PLAN>...</PLAN>
        match = re.search(r"<PLAN>(.*?)</PLAN>", plan_text, re.DOTALL)
        plan_json = None
        if match:
            try:
                plan_json = json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        if not plan_json:
            # Макс не смог сформировать план — возвращаем как обычный ответ
            return {
                "plan": None,
                "delegations": [],
                "agent_results": [],
                "final_summary": plan_text,
                "fallback": True,
            }

        delegations = plan_json.get("delegations", [])

        # ---- 2. Запускаем агентов параллельно ----
        def _run_one(d):
            slug = d.get("agent")
            task = d.get("task", "")
            if slug == "max" or slug not in {"leo", "anna", "zara", "eva"}:
                return None
            r = self.run_task(slug, task, brain_context=brain_context)
            return {
                "agent": slug,
                "agent_name": (find_agent(slug) or {}).get("name", slug),
                "task": task,
                "output": r.get("output", ""),
                "status": r.get("status"),
            }

        agent_results = []
        if delegations:
            with ThreadPoolExecutor(max_workers=4) as ex:
                for res in ex.map(_run_one, delegations):
                    if res:
                        agent_results.append(res)

        # ---- 3. Макс собирает финальный отчёт ----
        results_block = "\n\n".join(
            f"### {r['agent_name']} ({r['agent']})\n**Задача:** {r['task']}\n\n**Ответ:**\n{r['output']}"
            for r in agent_results
        ) or "(агенты не делегировались — отвечаешь только от себя)"

        summary_prompt = (
            f"Цель Айкерим: {goal}\n\n"
            f"План команды: {plan_json.get('plan', '')}\n\n"
            f"## Результаты команды\n\n{results_block}\n\n"
            f"{SUMMARY_INSTRUCTIONS}"
        )
        summary_response = self.run_task("max", summary_prompt, brain_context=brain_context)

        return {
            "plan": plan_json.get("plan"),
            "goal": plan_json.get("goal", goal),
            "delegations": delegations,
            "needs_data_from_aikerim": plan_json.get("needs_data_from_aikerim", []),
            "agent_results": agent_results,
            "final_summary": summary_response.get("output", ""),
            "fallback": False,
        }


def create_provider():
    kind = os.environ.get("VELA_PROVIDER", "mock").lower()
    if kind == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("⚠️  VELA_PROVIDER=claude, но ANTHROPIC_API_KEY не задан — fallback на mock")
            return MockAgentProvider()
        model = os.environ.get("VELA_MODEL", "claude-sonnet-4-5")
        print(f"✅ ClaudeAgentProvider активен, команда из {len(VELA_AGENTS)} агентов, модель={model}")
        return ClaudeAgentProvider(api_key=api_key, model=model)
    print(f"📋 MockAgentProvider активен (заглушки), команда из {len(VELA_AGENTS)} агентов")
    return MockAgentProvider()
