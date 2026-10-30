#!/bin/bash
# Orbitus — liga Gmail e iCloud ao painel (somente leitura, só cabeçalhos).
# Uso, no Terminal:  bash ~/System/Orbitus/App/configurar_email.sh
# As senhas de app vão para o Keychain do Mac (serviço "orbitus-email"), nunca para arquivo.
set -u
mkdir -p "$HOME/.orbitus"
CFG="$HOME/.orbitus/email.json"
APP="$(cd "$(dirname "$0")" && pwd)"
PY=$(for c in /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do [ -x "$c" ] && echo "$c" && break; done)

echo "== Orbitus · e-mails =="
echo "Aperte Enter para aceitar o endereço sugerido. Deixe a senha em branco para pular a conta."
echo

contas=()
pedir() { # nome host sugestao
  local nome=$1 host=$2 sug=$3 end senha
  read -r -p "$nome — endereço [$sug]: " end; end=${end:-$sug}
  read -r -s -p "$nome — senha de app (não aparece ao digitar): " senha; echo
  if [ -z "$senha" ]; then echo "  · $nome pulado"; return; fi
  senha=${senha// /}   # o Google mostra a senha em blocos com espaço
  security add-generic-password -U -s orbitus-email -a "$end" -w "$senha" -T /usr/bin/security >/dev/null \
    && echo "  ✓ senha guardada no Keychain"
  if ORB_P="$senha" "$PY" - "$host" "$end" <<'PYEOF'
import imaplib, os, sys
h, u = sys.argv[1:3]; p = os.environ['ORB_P']
try:
    m = imaplib.IMAP4_SSL(h, 993, timeout=20); m.login(u, p); m.select('INBOX', readonly=True); m.logout()
except Exception as e:
    print('  ✗ login recusado:', e); sys.exit(1)
PYEOF
  then echo "  ✓ $nome conectado"; contas+=("{\"nome\": \"$nome\", \"email\": \"$end\", \"host\": \"$host\"}")
  else echo "  → confira o endereço e gere outra senha de app"; fi
  echo
}

pedir Gmail  imap.gmail.com   mhmatos02@gmail.com
pedir iCloud imap.mail.me.com mhpmatos@icloud.com

if [ ${#contas[@]} -eq 0 ]; then echo "Nenhuma conta ligada. Nada foi alterado."; exit 1; fi
( IFS=,; echo "{\"contas\": [${contas[*]}]}" ) > "$CFG"
echo "✓ contas salvas em $CFG"
launchctl kickstart -k "gui/$(id -u)/com.orbitus.app" 2>/dev/null && echo "✓ app reiniciado" \
  || { echo "· serviço não instalado ainda; instalando"; bash "$APP/instalar.sh"; }
echo "Abra http://localhost:8787 — os e-mails aparecem em alguns segundos."
