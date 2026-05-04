#!/usr/bin/env bash
set -euo pipefail

# Start app
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >/tmp/uvicorn.log 2>&1 &
echo $! > /tmp/uvicorn.pid

# Give server a moment to start
sleep 3

# Run pytest for smart practice tests (fail on error)
pytest -q tests || (echo "Tests failed. Printing uvicorn log:"; cat /tmp/uvicorn.log; exit 1)
