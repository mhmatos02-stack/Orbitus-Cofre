#!/bin/bash
# Orbitus — instala o app como serviço do Mac (abre sozinho no login e reinicia se cair).
# Uso, no Terminal:  bash ~/System/Orbitus/App/instalar.sh
# Idempotente: pode rodar de novo depois de qualquer atualização.
set -u
APP="$(cd "$(dirname "$0")" && pwd)"
LABEL=com.orbitus.app
PL="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/.orbitus/app.log"
mkdir -p "$HOME/.orbitus" "$HOME/Library/LaunchAgents"

PY=""
for c in /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
  if [ -x "$c" ] && "$c" -c "import sys; assert sys.version_info >= (3,8)" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "✗ nenhum python3 utilizável. Rode: xcode-select --install"; exit 1; }

cat > "$PL" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$APP/server.py</string></array>
  <key>WorkingDirectory</key><string>$APP</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PL
plutil -lint "$PL" >/dev/null || { echo "✗ plist inválido"; exit 1; }
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PL" && echo "✓ serviço $LABEL carregado ($PY)"

for i in 1 2 3 4 5 6; do
  sleep 1
  if curl -fs http://localhost:8787/api/dados >/dev/null; then
    echo "✓ Orbitus no ar: http://localhost:8787"
    open http://localhost:8787
    exit 0
  fi
done
echo "✗ o app não respondeu. Últimas linhas do log:"; tail -20 "$LOG"; exit 1
