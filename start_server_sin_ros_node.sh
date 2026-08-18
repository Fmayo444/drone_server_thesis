#!/bin/bash
# Start the Sserver

export PYTHONPATH=$(pwd)
export MAVLINK_PORT=${MAVLINK_PORT:-14540}
export CLOUD_API_KEY=${CLOUD_API_KEY:-"default-dev-key"}

if [[ "$1" == "--silent" ]]; then
  export LOG_LEVEL="WARNING"
else
  export LOG_LEVEL=${LOG_LEVEL:-"INFO"}
fi

echo "==========================================================="
echo "Starting drone server for cloud services"
#echo "API Key required for access (default: default-dev-key)"
echo "Options: Pass --silent to disable connection logs"
echo "Docs available at: http://0.0.0.0:8080/docs"
echo "==========================================================="

uv run uvicorn src.server.server:app --host 0.0.0.0 --port 8080 --reload