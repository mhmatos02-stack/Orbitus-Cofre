#!/bin/bash
# Orbitus — garante que o Tailscale esteja aberto (acesso pelo celular).
# Abre o app no login e confere a cada 10 min; se alguém fechar, ele volta sozinho.
# Não depende da opção "Launch Tailscale at login" nem da lista de Itens de Início.
# Uso:  bash ~/System/Orbitus/App/instalar_tailscale_login.sh
# Desfazer:  launchctl bootout gui/$(id -u)/com.orbitus.tailscale; rm ~/Library/LaunchAgents/com.orbitus.tailscale.plist
set -u
LABEL=com.orbitus.tailscale
PL="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/.orbitus/tailscale.log"
APP=/Applications/Tailscale.app
[ -d "$APP" ] || { echo "✗ Tailscale não encontrado em $APP"; exit 1; }
mkdir -p "$HOME/.orbitus" "$HOME/Library/LaunchAgents"
cat > "$PL" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/usr/bin/open</string><string>-g</string><string>-a</string><string>$APP</string></array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>600</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PL
plutil -lint "$PL" >/dev/null || { echo "✗ plist inválido"; exit 1; }
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
if launchctl bootstrap "gui/$(id -u)" "$PL"; then
  echo "✓ Tailscale vai abrir em todo login (e reabrir se for fechado)"
else
  echo "✗ o macOS recusou. Veja Ajustes → Geral → Itens de Início e Extensões → Permitir em segundo plano"; exit 1
fi
sleep 3
if pgrep -xq Tailscale || pgrep -fq "$APP"; then echo "✓ Tailscale rodando agora"; else echo "… Tailscale ainda abrindo"; fi
"$APP/Contents/MacOS/Tailscale" serve status 2>/dev/null | head -2
