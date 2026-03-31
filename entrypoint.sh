#!/bin/bash

set -eo pipefail

# When using MySQL (OceanBase/seekdb), ensure database exists before bub starts
if [[ "${BUB_TAPESTORE_SQLALCHEMY_URL:-}" == *mysql* ]]; then
    /app/.venv/bin/python /app/scripts/create-bub-db.py || true
fi

if [ -f "/workspace/startup.sh" ]; then
    exec bash /workspace/startup.sh
else
    exec /app/.venv/bin/bubseek gateway
fi
