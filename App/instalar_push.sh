#!/bin/bash
# Orbitus — liga os avisos (Web Push) do próprio Orbitus no iPhone/Mac.
# Instala a biblioteca pywebpush para o Python do app, cria as chaves VAPID em ~/.orbitus (fora do cofre) e reinicia o app.
# Uso:  bash ~/System/Orbitus/App/instalar_push.sh
set -u
mkdir -p "$HOME/.orbitus"
PY=""
for c in /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
  if [ -x "$c" ] && "$c" -c "import sys; assert sys.version_info >= (3,8)" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "✗ nenhum python3 utilizável"; exit 1; }
# o app usa o python que está no agente com.orbitus.app; se for outro, prefere esse
PL="$HOME/Library/LaunchAgents/com.orbitus.app.plist"
if [ -f "$PL" ]; then
  APPY=$(/usr/libexec/PlistBuddy -c "Print :ProgramArguments:0" "$PL" 2>/dev/null)
  [ -x "$APPY" ] && PY="$APPY"
fi
echo "Python do app: $PY"
if ! "$PY" -c "import pywebpush" >/dev/null 2>&1; then
  "$PY" -m pip install --user --quiet pywebpush 2>/dev/null || "$PY" -m pip install --user --quiet --break-system-packages pywebpush || { echo "✗ não consegui instalar o pywebpush"; exit 1; }
fi
"$PY" -c "import pywebpush" || { echo "✗ pywebpush não carregou"; exit 1; }
echo "✓ biblioteca de push instalada"
if [ ! -f "$HOME/.orbitus/vapid_privada.pem" ]; then
  "$PY" - <<'PYEOF'
import os, base64
from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization
d = os.path.expanduser('~/.orbitus')
v = Vapid(); v.generate_keys()
v.save_key(os.path.join(d, 'vapid_privada.pem'))
pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
open(os.path.join(d, 'vapid_publica.txt'), 'w').write(base64.urlsafe_b64encode(pub).decode().rstrip('='))
os.chmod(os.path.join(d, 'vapid_privada.pem'), 0o600)
PYEOF
  echo "✓ chaves criadas em ~/.orbitus"
else
  echo "✓ chaves já existiam"
fi
launchctl kickstart -k "gui/$(id -u)/com.orbitus.app" && echo "✓ Orbitus reiniciado"
echo "Agora, no iPhone: abra o Orbitus pelo ícone da Tela de Início e toque em \"Ativar avisos\" embaixo da lista do dia."
