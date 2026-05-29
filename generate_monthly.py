#!/usr/bin/env python3
"""
Запускается systemd-timer'ом 1-го числа каждого месяца в 09:00.
Генерирует Vela Monthly Finance за прошедший месяц.
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
log = logging.getLogger("generate_monthly")


def main():
    from reports import generate_monthly
    md, meta = generate_monthly()
    log.info("Готов monthly: %d символов, month=%s", len(md), meta.get("month"))


if __name__ == "__main__":
    main()
