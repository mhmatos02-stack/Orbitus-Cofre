#!/usr/bin/env python3
# Backup diário do cofre Orbitus → git local + GitHub privado (launchd: com.orbitus.backup, 23:17).
# Mesmo princípio do backup do AI Wealth Office: sucesso só quando dá para PROVAR o invariante
# "não sobrou commit local por publicar" (rev-list origin/main..HEAD == 0). Sem remoto configurado,
# o resultado é ATENÇÃO (cópia só local), nunca sucesso.
# Grava o sinal em 00_Sistema/rotinas/backup.json, que o painel mostra em "Rotinas do Orbitus".
import datetime, json, os, shutil, subprocess

V = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIT = next((g for g in ("/Library/Developer/CommandLineTools/usr/bin/git", "/opt/homebrew/bin/git", "/usr/local/bin/git")
            if os.path.exists(g)), shutil.which("git") or "git")
os.chdir(V)


def git(*a):
    return subprocess.run([GIT, "-C", V, *a], capture_output=True, text=True)


def erro(r):
    """As linhas que explicam o erro (o git costuma pôr o motivo depois da primeira linha)."""
    t = (r.stderr or r.stdout or "").strip()
    ls = [l.strip() for l in t.splitlines() if l.strip() and not l.startswith("To ")]
    return " | ".join(ls)[:400] if ls else ("rc=%s" % r.returncode)


def head():
    r = git("rev-parse", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else None


def sinal(status, detalhe):
    p = os.path.join(V, "00_Sistema", "rotinas")
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, "backup.json"), "w", encoding="utf-8") as f:
        json.dump({"rotina": "backup", "quando": datetime.datetime.now().isoformat(timespec="minutes"),
                   "status": status, "detalhe": detalhe}, f, ensure_ascii=False, indent=1)
    print(status, "·", detalhe)


hoje = datetime.date.today().isoformat()
if not os.path.isdir(os.path.join(V, ".git")):
    r = git("init", "-b", "main")
    if r.returncode != 0:
        sinal("falha", "git init falhou: " + erro(r)); raise SystemExit(1)
    git("config", "user.name", "Orbitus")
    git("config", "user.email", "orbitus@localhost")

problemas = []
antes = head()
st = git("status", "--porcelain")
if st.returncode != 0:
    problemas.append("git status falhou: " + erro(st))
elif st.stdout.strip():
    a = git("add", "-A")
    if a.returncode != 0:
        problemas.append("git add falhou: " + erro(a))
    c = git("commit", "-m", "Snapshot automático %s" % hoje)
    if head() == antes:
        problemas.append("havia mudanças mas nenhum commit foi criado: " + erro(c))

if problemas:
    sinal("falha", "; ".join(problemas)); raise SystemExit(1)

if not git("remote").stdout.strip():
    sinal("atencao", "commit local feito (%s), mas sem GitHub: a cópia ainda está só neste Mac" % (head() or "")[:7])
    raise SystemExit(0)

p = git("push", "-u", "origin", "main")
pend = git("rev-list", "--count", "origin/main..HEAD")
if pend.returncode != 0:
    sinal("falha", "não consegui verificar o envio: " + erro(pend) + (" · push: " + erro(p) if p.returncode else ""))
    raise SystemExit(1)
if pend.stdout.strip() != "0":
    sinal("falha", "%s commit(s) não enviados ao GitHub: %s" % (pend.stdout.strip(), erro(p)))
    raise SystemExit(1)
sinal("ok", "cofre salvo no GitHub (%s)" % (head() or "")[:7])
