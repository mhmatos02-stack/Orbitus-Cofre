# -*- coding: utf-8 -*-
"""Orbitus — e-mails (Gmail + iCloud via IMAP, somente leitura): pedem resposta, não lidos e recentes, com prévia.

Contas em ~/.orbitus/email.json; senhas de app no Keychain do macOS (serviço "orbitus-email",
conta = endereço). Nada é marcado como lido: a caixa é aberta em modo leitura e usa BODY.PEEK.
Critério de "pede resposta": não lido, últimos 14 dias, de uma pessoa (não lista, não robô).
Prévia: até 24 KB de cada mensagem (BODY.PEEK[]<0.24000>), só para extrair as primeiras linhas; nada é gravado em disco.
"""
import html as html_mod
import email, email.header, email.utils, imaplib, json, os, re, subprocess, time
from datetime import datetime, timedelta

CFG = os.path.expanduser('~/.orbitus/email.json')
CACHE = {'t': 0, 'dados': None}
TTL = 600
ROBO = re.compile(r'no-?reply|nao-?responda|não-?responda|notifica|newsletter|mailer-daemon|postmaster|'
                  r'bounce|alert|info@|news@|marketing|promo|suporte@|support@|updates?@|digest', re.I)


def _senha(conta):
    try:
        r = subprocess.run(['security', 'find-generic-password', '-s', 'orbitus-email', '-a', conta, '-w'],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _dec(v):
    try:
        return str(email.header.make_header(email.header.decode_header(v or ''))).strip()
    except Exception:
        return (v or '').strip()


UIDRE = re.compile(rb'UID (\d+)')
FLAGRE = re.compile(rb'FLAGS \(([^)]*)\)')


def _texto(msg):
    """Prévia: primeiro text/plain; senão o HTML sem tags. Corta citações e espaços."""
    plain, html = None, None
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        ct = part.get_content_type()
        if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition', '').startswith('attachment'):
            continue
        try:
            raw = part.get_payload(decode=True) or b''
            txt = raw.decode(part.get_content_charset() or 'utf-8', 'replace')
        except Exception:
            continue
        if ct == 'text/plain' and plain is None:
            plain = txt
        elif ct == 'text/html' and html is None:
            html = txt
    t = plain
    if not t and html:
        t = re.sub(r'(?is)<(script|style|head).*?</\1>', ' ', html)
        t = re.sub(r'(?s)<[^>]+>', ' ', t)
        t = html_mod.unescape(t).replace('\xa0', ' ')
    if not t:
        return ''
    linhas = []
    for l in t.splitlines():
        l = l.strip()
        if l.startswith('>') or re.match(r'^(On|Em) .{5,120}(wrote|escreveu):?$', l):
            break
        if l:
            linhas.append(l)
    return re.sub(r'\s+', ' ', ' '.join(linhas))[:240]


def _uma_conta(c, eu):
    """Recentes (7 dias) + não lidos (14 dias), cada um com prévia. Somente leitura (BODY.PEEK)."""
    senha = _senha(c['email'])
    if not senha:
        return [], 0, 'sem senha no Keychain'
    m = imaplib.IMAP4_SSL(c['host'], 993, timeout=25)
    try:
        m.login(c['email'], senha)
        m.select('INBOX', readonly=True)
        d14 = (datetime.now() - timedelta(days=14)).strftime('%d-%b-%Y')
        d7 = (datetime.now() - timedelta(days=7)).strftime('%d-%b-%Y')
        _, a = m.uid('search', None, '(UNSEEN SINCE %s)' % d14)
        nao_lidos = a[0].split() if a and a[0] else []
        _, b = m.uid('search', None, '(SINCE %s)' % d7)
        recentes = b[0].split() if b and b[0] else []
        uids = sorted(set(nao_lidos[-60:]) | set(recentes[-50:]), key=int)
        out = []
        for k in range(0, len(uids), 20):
            _, f = m.uid('fetch', b','.join(uids[k:k + 20]), '(FLAGS BODY.PEEK[]<0.24000>)')
            for x in f:
                if not isinstance(x, tuple):
                    continue
                meta, raw = x[0], x[1]
                um = UIDRE.search(meta)
                fm = FLAGRE.search(meta)
                lido = b'\\Seen' in (fm.group(1) if fm else b'')
                h = email.message_from_bytes(raw)
                nome, end = email.utils.parseaddr(_dec(h.get('From')))
                massa = bool(h.get('List-Unsubscribe') or h.get('List-Id')
                             or (h.get('Precedence') or '').lower() in ('bulk', 'list', 'junk')
                             or (h.get('Auto-Submitted') or 'no').lower() != 'no' or ROBO.search(end or ''))
                if (end or '').lower() in eu:
                    continue
                try:
                    quando = email.utils.parsedate_to_datetime(h.get('Date')).astimezone().replace(tzinfo=None)
                except Exception:
                    quando = None
                try:
                    previa = _texto(h)
                except Exception:
                    previa = ''
                out.append({'conta': c['nome'], 'uid': um.group(1).decode() if um else '', 'de': nome or end, 'email': end,
                            'assunto': _dec(h.get('Subject')) or '(sem assunto)',
                            'quando': quando.isoformat(timespec='minutes') if quando else '',
                            'mid': (h.get('Message-ID') or '').strip().strip('<>'), 'lido': lido,
                            'pessoa': not massa, 'pede': (not lido) and (not massa) and quando is not None
                            and quando >= datetime.now() - timedelta(days=14), 'previa': previa})
        return out, len(nao_lidos), None
    finally:
        try:
            m.logout()
        except Exception:
            pass


import threading
_TRAVA = threading.Lock()


def carregar():
    """Devolve o último retrato na hora; se estiver velho, atualiza em segundo plano."""
    if time.time() - CACHE['t'] > TTL and _TRAVA.acquire(blocking=False):
        CACHE['t'] = time.time()
        def _rodar():
            try:
                CACHE['dados'] = _buscar()
            finally:
                _TRAVA.release()
        threading.Thread(target=_rodar, daemon=True).start()
    return CACHE['dados'] or {'configurado': os.path.exists(CFG), 'carregando': True, 'itens': [], 'contas': []}


def _buscar():
    try:
        with open(CFG, encoding='utf-8') as f:
            contas = json.load(f).get('contas', [])
    except (OSError, ValueError):
        contas = []
    if not contas:
        return {'configurado': False, 'itens': [], 'contas': []}
    eu = {c['email'].lower() for c in contas}
    todos, resumo = [], []
    for c in contas:
        try:
            lst, tot, erro = _uma_conta(c, eu)
        except Exception as e:
            lst, tot, erro = [], 0, str(e)[:120]
        todos += lst
        resumo.append({'nome': c['nome'], 'nao_lidos': tot, 'pedem': sum(1 for x in lst if x['pede']), 'erro': erro})
    todos.sort(key=lambda x: x['quando'], reverse=True)
    # 'itens' = os que pedem resposta (o resto do painel usa esta chave); 'todos' alimenta as abas
    return {'configurado': True, 'itens': [x for x in todos if x['pede']][:30], 'todos': todos[:120],
            'contas': resumo, 'atualizado': datetime.now().strftime('%H:%M')}
