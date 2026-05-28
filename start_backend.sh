#!/bin/bash
export PATH="$HOME/.local/bin:/usr/bin:$PATH"
cd "/mnt/d/hermes agent/2026世界杯分析/backend" || exit 1
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
