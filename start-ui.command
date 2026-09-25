#!/bin/bash
# That's Not My Name — start local web UI
cd "$(dirname "$0")"
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

if [[ ! -x .venv/bin/python3 ]]; then
  echo "Missing .venv — create it and install requirements.txt first."
  read -r
  exit 1
fi

.venv/bin/python3 -c "import flask" 2>/dev/null || .venv/bin/pip install -q flask==3.1.0
pkill -f "python3 web_ui.py" 2>/dev/null || true
sleep 0.3
open -na "Google Chrome" --args --new-window "http://127.0.0.1:8765/" 2>/dev/null \
  || open -na "Safari" "http://127.0.0.1:8765/" 2>/dev/null \
  || open "http://127.0.0.1:8765/"
exec .venv/bin/python3 web_ui.py --no-browser
