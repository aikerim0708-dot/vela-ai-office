#!/bin/bash
# Запуск VELA AI Office.
# Использование: ./run.sh
# Останавливать: Ctrl+C

cd "$(dirname "$0")"
source .venv/bin/activate

# --reload-dir .             — следить только за текущей папкой backend/
# --reload-exclude .venv     — НЕ следить за виртуальным окружением (там 100k+ файлов библиотек)
# --reload-exclude data      — НЕ следить за SQLite и uploads (они меняются при работе)
# --reload-exclude __pycache__ — кэш Python
exec uvicorn app:app \
    --port 8000 \
    --host 127.0.0.1 \
    --reload \
    --reload-dir . \
    --reload-exclude ".venv/*" \
    --reload-exclude "data/*" \
    --reload-exclude "__pycache__/*"
