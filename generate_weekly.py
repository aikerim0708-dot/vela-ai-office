#!/usr/bin/env python3
"""
Запускается systemd-timer'ом каждое воскресенье в 21:00.
Генерирует Vela Weekly за прошедшую неделю.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("generate_weekly")


def main():
    from reports import generate_weekly
    md, meta = generate_weekly()
    log.info("Готов weekly: %d символов, week_id=%s", len(md), meta.get("week_id"))


if __name__ == "__main__":
    main()
