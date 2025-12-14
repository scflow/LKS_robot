#!/bin/bash

#!/bin/bash

# 简单启动脚本：仅运行当前项目的 app.py（Flask + 摄像头线程）

set -e

APP_PID=""

cleanup() {
  echo ""
  echo "Stopping app.py ..."
  if [[ -n "$APP_PID" ]] && ps -p "$APP_PID" > /dev/null 2>&1; then
    kill "$APP_PID"
  fi
  exit 0
}

trap cleanup SIGINT SIGTERM

echo "Starting app.py ..."
python3 app.py &
APP_PID=$!

wait "$APP_PID"
