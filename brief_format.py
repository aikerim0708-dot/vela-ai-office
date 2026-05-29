"""
Формат структурированного brief — единый для всех агентов VELA.

Идея из урока 4 курса AI Room: агент возвращает НЕ свободный текст, а
структуру с источниками. Можно ревьюить, легко парсить, видно
откуда вывод.

Использование:
    from brief_format import BRIEF_INSTRUCTION, parse_brief

    system_prompt = base_prompt + BRIEF_INSTRUCTION
    ...
    parsed = parse_brief(agent_output)  # → Brief | None
"""
from __future__ import annotations

import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ────────── Инструкция для системного промпта агента ──────────
BRIEF_INSTRUCTION = """

## Формат ответа

Любой содержательный ответ возвращай в формате **brief** (markdown). Это единый формат для всех агентов VELA — он даёт прозрачность откуда вывод и можно ревьюить.

```markdown
## Aim
Что именно я выяснял (одна фраза).

## Confidence
high / medium / low

## Sources
- Источник 1 (точное название + точный запрос/параметры)
- Источник 2

## Findings
1. Главный факт с числом.
2. Второй факт.
3. (по необходимости)

## Contradictions / Uncertainties
- Если что-то не сходится или есть риск — пиши сюда.
- Если ничего — пиши «нет».

## Handoff
- Что предлагаю сделать дальше.
- К кому передать (Ева/Лео/Анна/Зара) если нужно.
- Что попросить уточнить у Айкерим.
```

**Правила формата:**
- Если данных нет — `confidence: low` и `[нет данных]` в Findings, не выдумывай.
- Sources обязательны. Если источник = WB API — указывай endpoint + параметры запроса.
- Не делай brief на «привет» / болтовню — на это отвечай обычно.
- Контекст из контекстной папки (`docs/<agent>-context/`) тоже считай за источник.
"""


# ────────── Pydantic-модель для парсинга/валидации ──────────
ConfidenceLevel = Literal["high", "medium", "low"]


class Brief(BaseModel):
    """Структурированный ответ агента VELA."""

    aim: str = Field(..., description="Что именно агент выяснял")
    confidence: ConfidenceLevel = Field(..., description="Уровень уверенности")
    sources: List[str] = Field(default_factory=list, description="Откуда взяты данные")
    findings: List[str] = Field(default_factory=list, description="Главные выводы")
    contradictions: List[str] = Field(
        default_factory=list, description="Противоречия / неопределённости"
    )
    handoff: Optional[str] = Field(
        None, description="Что предлагает агент сделать дальше"
    )

    # raw — оригинальный текст ответа, на случай если brief не разобрался полностью
    raw: Optional[str] = None


# ────────── Парсер ──────────
_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def parse_brief(text: str) -> Optional[Brief]:
    """Достаёт brief из markdown-ответа агента.

    Если структура не распознана (агент вернул свободный текст) — возвращает None.
    Тогда вызывающий код может использовать text как есть.
    """
    if not text or not text.strip():
        return None

    # Разбиваем на секции по ## заголовкам
    sections = _split_sections(text)

    if not sections or "aim" not in sections:
        # Без Aim это не brief, а свободный текст
        return None

    confidence_raw = sections.get("confidence", "").strip().lower()
    confidence: ConfidenceLevel = "medium"
    if confidence_raw.startswith("high"):
        confidence = "high"
    elif confidence_raw.startswith("low"):
        confidence = "low"
    elif confidence_raw.startswith("medium") or confidence_raw.startswith("med"):
        confidence = "medium"

    try:
        return Brief(
            aim=sections.get("aim", "").strip()[:1000] or "—",
            confidence=confidence,
            sources=_parse_list(sections.get("sources", "")),
            findings=_parse_list(sections.get("findings", "")),
            contradictions=_parse_list(
                sections.get("contradictions", "")
                or sections.get("contradictions / uncertainties", "")
            ),
            handoff=sections.get("handoff", "").strip() or None,
            raw=text,
        )
    except Exception:
        return None


def _split_sections(text: str) -> dict:
    """Разбивает markdown по ## заголовкам в dict {lower_name: content}."""
    result: dict = {}
    matches = list(_HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        name = m.group(1).strip().lower()
        # Уберём знаки препинания в конце для устойчивости
        name = name.rstrip(":")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        result[name] = body
    return result


def _parse_list(s: str) -> List[str]:
    """Достаёт элементы списка — поддерживает `-`, `*`, `1.`, `2.` префиксы."""
    if not s.strip():
        return []
    items: List[str] = []
    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue
        # убираем bullet/число-префикс
        line = re.sub(r"^([-*+]|\d+\.)\s+", "", line)
        if line:
            items.append(line)
    return items
