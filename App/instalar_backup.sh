#!/bin/bash
# Orbitus — instala o backup diário do cofre (23:17, e também ao ligar o Mac) e roda a primeira vez.
# Uso:  bash ~/System/Orbitus/App/instalar_backup.sh  [URL do repositório privado no GitHub]
set -u
V="$(cd "$(dirname "$0")/.." && pwd)"
LABEL=com.orbitus.backup
PL="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/.orbitus/backup.log"
mkdir -p "$HOME/.orbitus" "$HOME/Library/LaunchAgents"
PY=""
for c in /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
  if [ -x "$c" ] && "$c" -c "import sys; assert sys.version_info >= (3,8)" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "✗ nenhum python3 utilizável"; exit 1; }
if [ $# -ge 1 ]; then
  [ -d "$V/.git" ] || git -C "$V" init -b main >/dev/null
  git -C "$V" remote remove origin 2>/dev/null
  git -C "$V" remote add origin "$1" && echo "✓ GitHub configurado: $1"
fi
cat > "$PL" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$V/Scripts/backup_orbitus.py</string></array>
  <key>WorkingDirectory</key><string>$V</string>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>17</integer></dict>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PL
plutil -lint "$PL" >/dev/null || { echo "✗ plist inválido"; exit 1; }
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PL" && echo "✓ backup diário agendado para 23:17 e ao ligar o Mac"
echo "Primeira execução:"; "$PY" "$V/Scripts/backup_orbitus.py"
