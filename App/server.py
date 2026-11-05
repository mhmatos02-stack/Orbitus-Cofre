#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orbitus — app local. O cofre Obsidian é a base de dados; este servidor só lê e grava arquivos dele.

Uso:  python3 App/server.py            → http://localhost:8787
Só biblioteca padrão. Escuta apenas em 127.0.0.1 (o painel mostra dados financeiros).

Fontes:
  10_Tarefas/*.md             tarefas no formato do plugin Tasks (- [ ] texto 📅 AAAA-MM-DD #financas)
  01_Federacao/*.md           saúde dos sistemas (gerado por Scripts/coletar_federacao.py, rodado aqui)
  00_Sistema/marcos.json      marcos com data (viagem etc.)
  00_Sistema/treino.json      resumo do treino
  00_Sistema/agenda.json      agenda (snapshot); se ~/.orbitus/agenda.txt tiver links ICS, eles têm prioridade
"""
import json, os, re, sys, threading, time, urllib.request
from datetime import date, datetime, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

APP = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.dirname(APP)
STATIC = os.path.join(APP, 'static')
HOME_CFG = os.path.expanduser('~/.orbitus')
PORT = int(os.environ.get('ORBITUS_PORT', '8787'))
LOCK = threading.Lock()

sys.path.insert(0, os.path.join(VAULT, 'Scripts'))
sys.path.insert(0, APP)
import emails
import wealth_rotinas
import mesa
import wealth
import viagem
import treino
import concierge
import rotina
import tarefas_api
import push
import agenda_pro
import cio
import diario
concierge.AGUA_FN = lambda n: rotina.agua_somar(VAULT, date.today().isoformat(), n)
concierge.PESO_FN = lambda kg: treino.registrar_saude(VAULT, {'peso': kg})
concierge.PASSOS_FN = lambda n: treino.registrar_saude(VAULT, {'passos': n})

TASK_RE = re.compile(r'^(\s*[-*] \[)([ xX])(\] )(.*)$')
DUE_RE = re.compile(r'📅\s*(\d{4}-\d{2}-\d{2})')
DONE_RE = re.compile(r'✅\s*(\d{4}-\d{2}-\d{2})')
PRIO = {'🔺': 0, '⏫': 1, '🔼': 2, '🔽': 4}
FIN_TAGS = ('#financas', '#finanças', '#wealth')


def ler(p, default=None):
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return default


def ler_json(p, default):
    t = ler(p)
    try:
        return json.loads(t) if t else default
    except ValueError:
        return default


# ---------------------------------------------------------------- tarefas
def limpar_titulo(txt):
    t = DUE_RE.sub('', txt)
    t = DONE_RE.sub('', t)
    t = rotina.HORA_TXT.sub('', t)
    for e in list(PRIO) + ['⏳', '🛫', '➕', '🔁']:
        t = re.sub(re.escape(e) + r'\s*(\d{4}-\d{2}-\d{2})?', '', t)
    t = re.sub(r'(^|\s)#[\w\-/À-ÿ]+', ' ', t)
    fonte = ''
    m = re.search(r'\s[—–-]{1,2}\s(.+)$', t)
    if m:
        fonte, t = m.group(1).strip(), t[:m.start()]
    return re.sub(r'\s+', ' ', t).strip(), fonte


def tarefas(hoje):
    pasta = os.path.join(VAULT, '10_Tarefas')
    out = []
    for raiz, _, arqs in os.walk(pasta):
        for a in sorted(arqs):
            if not a.endswith('.md'):
                continue
            p = os.path.join(raiz, a)
            rel = os.path.relpath(p, VAULT)
            for i, linha in enumerate((ler(p) or '').splitlines()):
                m = TASK_RE.match(linha)
                if not m:
                    continue
                corpo, feito = m.group(4), m.group(2).lower() == 'x'
                dm = DONE_RE.search(corpo)
                if feito:
                    continue  # concluída sai da tela na hora (2026-10-30); o histórico fica no arquivo
                due = DUE_RE.search(corpo)
                due = due.group(1) if due else ''
                prio = min([PRIO[e] for e in PRIO if e in corpo] or [3])
                info = tarefas_api.ler_linha(linha) or {}
                tag = info.get('area') or 'Pessoal'
                titulo, fonte = (info['titulo'], info['fonte']) if info.get('titulo') else limpar_titulo(corpo)
                if due and due <= hoje.isoformat() or prio == 0:
                    col = 'hoje'
                elif due and due <= (hoje + timedelta(days=7)).isoformat():
                    col = 'semana'
                else:
                    col = 'depois'
                out.append({'arquivo': rel, 'linha': i, 'texto': linha, 'titulo': titulo, 'fonte': fonte, 'hora': rotina.hora_da_tarefa(corpo),
                            'status': info.get('status', ''), 'repete': info.get('repete', ''), 'url': info.get('url', ''), 'criada': info.get('criada', ''),
                            'tag': tag, 'due': due, 'prio': prio, 'feito': feito, 'col': col,
                            'atrasada': bool(due and due < hoje.isoformat() and not feito)})
    out.sort(key=lambda t: (t['feito'], t['prio'], t['due'] or '9999'))
    return out


def tarefas_do_dia(d_iso):
    """Tarefas com data nesse dia (feitas ou não); no dia de hoje, também as atrasadas ainda abertas."""
    hoje = date.today().isoformat()
    out = []
    for raiz, _, arqs in os.walk(os.path.join(VAULT, '10_Tarefas')):
        for a in sorted(arqs):
            if not a.endswith('.md'):
                continue
            p = os.path.join(raiz, a)
            for i, linha in enumerate((ler(p) or '').splitlines()):
                m = TASK_RE.match(linha)
                if not m:
                    continue
                corpo, feito = m.group(4), m.group(2).lower() == 'x'
                due = DUE_RE.search(corpo)
                due = due.group(1) if due else ''
                feita = DONE_RE.search(corpo)
                atrasada = bool(not feito and due and due < d_iso and d_iso == hoje)
                if not (due == d_iso or atrasada or (feito and feita and feita.group(1) == d_iso and due and due < d_iso)):
                    continue
                out.append({'arquivo': os.path.relpath(p, VAULT), 'linha': i, 'linha_txt': linha, 'hora': rotina.hora_da_tarefa(corpo),
                            'texto': (tarefas_api.ler_linha(linha) or {}).get('titulo') or limpar_titulo(corpo)[0], 'feito': feito, 'atrasada': atrasada, 'due': due})
    return out


def _sugestoes():
    try:
        ms = treino.mesa(VAULT)
        ms = {'ultimo_parecer': (ms.get('pareceres') or [None])[0]}
    except Exception:
        ms = {}
    return tarefas_api.sugestoes(VAULT, dados(), ms)


def _cio_fluxo(prep):
    """Streaming da resposta do CIO, com o gasto somado ao mesmo teto mensal do Concierge.
    Análises longas: espera de até 5 min (antes o plano B cortava em 90 s e a resposta saía vazia)."""
    texto, us, parada = '', {}, ''
    for ev in concierge._stream(prep['corpo'], prep['chave'], espera=100):
        tp = ev.get('type')
        if tp == 'message_start':
            us.update((ev.get('message') or {}).get('usage') or {})
        elif tp == 'content_block_delta' and (ev.get('delta') or {}).get('type') == 'text_delta':
            x = ev['delta'].get('text', '')
            texto += x
            yield {'t': 'delta', 'x': x}
        elif tp == 'message_delta':
            us.update(ev.get('usage') or {})
            parada = (ev.get('delta') or {}).get('stop_reason') or parada
        elif tp == 'error':
            raise RuntimeError('a API respondeu: ' + (ev.get('error') or {}).get('message', 'erro'))
    if parada == 'max_tokens' and texto.strip():
        nota = '\n\n_(A resposta foi cortada no limite de tamanho. Peça "continue" para o resto.)_'
        texto += nota
        yield {'t': 'delta', 'x': nota}
    if not texto.strip():
        raise RuntimeError('o CIO não devolveu texto (%s). Tente de novo; se repetir, peça em partes menores.' % (parada or 'conexão encerrada antes da resposta'))
    cio.finalizar(prep, texto.strip(), VAULT)
    pi, po = concierge.PRECO.get(concierge.MODELO, (2.0, 10.0))
    custo = (us.get('input_tokens', 0) * pi + us.get('cache_creation_input_tokens', 0) * pi * 1.25 +
             us.get('cache_read_input_tokens', 0) * pi * 0.1 + us.get('output_tokens', 0) * po) / 1e6
    with concierge.TRAVA:
        u = concierge._uso()
        u['usd'] = u.get('usd', 0) + custo
        u['perguntas'] = u.get('perguntas', 0) + 1
        concierge._gravar_uso(u)
    yield {'t': 'fim', 'resposta': texto.strip(), 'custo_usd': round(custo, 4), 'mes_usd': round(u['usd'], 4), 'teto': u.get('teto', concierge.TETO_PADRAO),
           'cache': us.get('cache_read_input_tokens', 0)}


def agenda_proativa(dias=45):
    d = dados()
    try:
        vs = [viagem.estado(VAULT, v['id']) for v in viagem.listar(VAULT)]
    except Exception:
        vs = []
    try:
        w = wealth.estado(VAULT)
    except Exception:
        w = {}
    lt = {}
    for l in (ler_json(os.path.join(VAULT, '20_Treino', 'locais.json'), {}) or {}).get('locais') or []:
        try:
            a, b = date.fromisoformat(l['de']), date.fromisoformat(l.get('ate') or l['de'])
        except (KeyError, ValueError):
            continue
        while a <= b:
            lt[a.isoformat()] = l.get('local', '')
            a += timedelta(days=1)
    return agenda_pro.montar(d['eventos'], d['tarefas'], vs, w, lt, dias)


def dia_ordenado(d_iso):
    ev = (agenda(date.today())[0] or {}).get(d_iso, [])
    r = rotina.dia(VAULT, d_iso, tarefas_do_dia(d_iso), ev)
    if d_iso <= date.today().isoformat():
        try:
            r['wealth_rotinas'] = wealth_rotinas.do_dia(mesa.pasta_wealth(VAULT), date.fromisoformat(d_iso))
        except Exception as e:
            r['wealth_rotinas'] = {'ok': False, 'erro': str(e)[:160], 'itens': []}
    if d_iso == date.today().isoformat():
        tr = _treino_resumo() or {}
        if tr.get('data') == d_iso and tr.get('sessao_nome'):
            for x in r['itens']:
                if x.get('liga') == 'treino':
                    x['detalhe'] = tr['sessao_nome']
    return r


def alternar(arquivo, linha, texto):
    p = os.path.normpath(os.path.join(VAULT, arquivo))
    if not p.startswith(os.path.join(VAULT, '10_Tarefas')) or not p.endswith('.md'):
        raise ValueError('arquivo fora de 10_Tarefas')
    with LOCK:
        linhas = (ler(p) or '').split('\n')
        if linha >= len(linhas) or linhas[linha] != texto:
            raise ValueError('a tarefa mudou no Obsidian; recarregue o painel')
        m = TASK_RE.match(linhas[linha])
        proxima = None
        if m.group(2) == ' ':
            nova = m.group(1) + 'x' + m.group(3) + m.group(4).rstrip() + ' ✅ ' + date.today().isoformat()
            linhas[linha] = nova
            proxima = tarefas_api.concluir_com_repeticao(linhas, linha, date.today().isoformat())
            if proxima:
                linha += 1          # a próxima ocorrência entrou logo acima
        else:
            nova = m.group(1) + ' ' + m.group(3) + DONE_RE.sub('', m.group(4)).rstrip()
            linhas[linha] = nova
            # desfazendo uma repetição: tira a ocorrência que tinha sido criada logo acima, se ainda estiver intacta
            f0 = tarefas_api.ler_linha(nova) or {}
            if f0.get('repete') and linha > 0:
                ac = tarefas_api.ler_linha(linhas[linha - 1]) or {}
                if ac and not ac['feito'] and ac['titulo'] == f0['titulo'] and ac['repete'] == f0['repete'] and ac['criada'] == date.today().isoformat():
                    del linhas[linha - 1]
                    linha -= 1
        with open(p, 'w', encoding='utf-8') as f:
            f.write('\n'.join(linhas))
        return nova, linha, proxima


def capturar(texto):
    texto = re.sub(r'[\r\n]+', ' ', texto).strip()[:300]
    if not texto:
        raise ValueError('texto vazio')
    p = os.path.join(VAULT, '10_Tarefas', 'Tarefas.md')
    with LOCK:
        conteudo = ler(p) or '# Tarefas\n\n## Inbox\n'
        linhas = conteudo.split('\n')
        try:
            i = next(k for k, l in enumerate(linhas) if l.strip().lower() == '## inbox') + 1
            while i < len(linhas) and linhas[i].strip() == '':
                i += 1
            while i < len(linhas) and TASK_RE.match(linhas[i]):
                i += 1
        except StopIteration:
            linhas += ['', '## Inbox', '']
            i = len(linhas)
        linhas.insert(i, '- [ ] ' + texto + ' ➕ ' + date.today().isoformat())
        with open(p, 'w', encoding='utf-8') as f:
            f.write('\n'.join(linhas))


# ---------------------------------------------------------------- federação
def federacao():
    try:
        import coletar_federacao
        coletar_federacao.HOJE = date.today()
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            coletar_federacao.main()
    except Exception as e:  # o painel continua com o último retrato
        print('federação:', e, file=sys.stderr)
    out = []
    pasta = os.path.join(VAULT, '01_Federacao')
    for a in sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []:
        t = ler(os.path.join(pasta, a)) or ''
        m = re.match(r'^---\n(.*?)\n---', t, re.S)
        if not m:
            continue
        d, chave = {}, None
        for l in m.group(1).split('\n'):
            if l.startswith('  - ') and chave:
                try:
                    d.setdefault(chave, []).append(json.loads(l[4:]))
                except ValueError:
                    d.setdefault(chave, []).append(l[4:])
            elif ':' in l:
                chave, v = l.split(':', 1)
                v = v.strip()
                try:
                    d[chave] = [] if v in ('', '[]') else json.loads(v)
                except ValueError:
                    d[chave] = v
        out.append(d)
    return out


# ---------------------------------------------------------------- agenda
ICS_CACHE = {'t': 0, 'ev': None}


def _ics_dt(v):
    """Valor de DTSTART/EXDATE/UNTIL → (datetime local ingênuo, dia_todo)."""
    v = v.strip()
    if re.fullmatch(r'\d{8}', v):
        return datetime.strptime(v, '%Y%m%d'), True
    dt = datetime.strptime(v[:15], '%Y%m%dT%H%M%S')
    if v.endswith('Z'):
        dt -= timedelta(hours=3)  # UTC → Brasília (sem horário de verão desde 2019)
    return dt, False


WD = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}


def _somar_meses(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    for dia in (d.day, 30, 29, 28):
        try:
            return d.replace(year=y, month=m, day=dia) if dia == d.day else None
        except ValueError:
            return None  # mês sem esse dia: RFC 5545 pula a ocorrência
    return None


def _ocorrencias(inicio, regra, fim_janela):
    """Expande RRULE (DAILY/WEEKLY/MONTHLY/YEARLY, INTERVAL, COUNT, UNTIL, BYDAY semanal)."""
    r = dict(p.split('=', 1) for p in regra.split(';') if '=' in p)
    freq, passo = r.get('FREQ'), int(r.get('INTERVAL', '1'))
    limite = int(r['COUNT']) if 'COUNT' in r else None
    ate = _ics_dt(r['UNTIL'])[0] if 'UNTIL' in r else None
    dias_sem = [WD[x[-2:]] for x in r.get('BYDAY', '').split(',') if x[-2:] in WD] if freq == 'WEEKLY' else []
    n, k = 0, 0
    while k < 3000:
        if freq == 'DAILY':
            cands = [inicio + timedelta(days=k * passo)]
        elif freq == 'WEEKLY':
            base = inicio + timedelta(weeks=k * passo)
            seg = base - timedelta(days=base.weekday())
            cands = sorted(seg + timedelta(days=w) for w in (dias_sem or [inicio.weekday()]))
            cands = [c for c in cands if c >= inicio]
        elif freq == 'MONTHLY':
            c = _somar_meses(inicio, k * passo)
            cands = [c] if c else []
        elif freq == 'YEARLY':
            c = _somar_meses(inicio, 12 * k * passo)
            cands = [c] if c else []
        else:
            return
        for c in cands:
            if (ate and c > ate) or (limite is not None and n >= limite) or c > fim_janela:
                return
            n += 1
            yield c
        k += 1


def baixar(u):
    """urllib primeiro; se o Python do Mac recusar o certificado, usa o curl do sistema (Keychain)."""
    try:
        with urllib.request.urlopen(u, timeout=15) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception as e1:
        import subprocess
        r = subprocess.run(['/usr/bin/curl', '-fsSL', '--max-time', '20', u], capture_output=True, timeout=25)
        if r.returncode != 0:
            raise RuntimeError('%s | curl: %s' % (e1, r.stderr.decode('utf-8', 'replace').strip()[:80]))
        return r.stdout.decode('utf-8', 'replace')


def ler_ics(texto, ini, fim):
    ev = {}
    texto = re.sub(r'\r?\n[ \t]', '', texto)
    j_ini = datetime.fromisoformat(ini)
    j_fim = datetime.fromisoformat(fim) + timedelta(days=1)
    blocos, trocas = [], {}
    for bloco in re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', texto, re.S):
        campos, exd = {}, set()
        for l in bloco.strip().splitlines():
            if ':' not in l:
                continue
            k, v = l.split(':', 1)
            k = k.split(';')[0]
            if k == 'EXDATE':
                for x in v.split(','):
                    try:
                        exd.add(_ics_dt(x)[0].date())
                    except ValueError:
                        pass
            else:
                campos[k] = v
        if 'DTSTART' not in campos:
            continue
        campos['_exd'] = exd
        if 'RECURRENCE-ID' in campos:  # ocorrência editada de um evento que se repete
            try:
                trocas.setdefault(campos.get('UID'), set()).add(_ics_dt(campos['RECURRENCE-ID'])[0].date())
            except ValueError:
                pass
        blocos.append(campos)
    for c in blocos:
        if c.get('STATUS') == 'CANCELLED':
            continue
        try:
            inicio, dia_todo = _ics_dt(c['DTSTART'])
        except ValueError:
            continue
        titulo = c.get('SUMMARY', '(sem título)').replace('\\,', ',').replace('\\;', ';').replace('\\n', ' ')
        livre = c.get('TRANSP') == 'TRANSPARENT' or dia_todo
        hora = 'dia todo' if dia_todo else inicio.strftime('%H:%M')
        if 'RRULE' in c and 'RECURRENCE-ID' not in c:
            pular = c['_exd'] | trocas.get(c.get('UID'), set())
            datas = (o for o in _ocorrencias(inicio, c['RRULE'], j_fim) if o.date() not in pular)
        else:
            datas = [inicio]
        for o in datas:
            if j_ini <= o < j_fim:
                ev.setdefault(o.date().isoformat(), []).append([hora, titulo, 'r' if livre else 'b'])
    return ev


def agenda(hoje):
    ini, fim = (hoje - timedelta(days=7)).isoformat(), (hoje + timedelta(days=90)).isoformat()
    urls = [re.sub(r'^webcals?://', 'https://', l.strip()) for l in (ler(os.path.join(HOME_CFG, 'agenda.txt')) or '').splitlines()
            if re.match(r'^(https?|webcals?)://', l.strip())]
    if urls:
        if time.time() - ICS_CACHE['t'] > 900 or ICS_CACHE['ev'] is None:
            ev, erros = {}, []
            for u in urls:
                nome = 'Google' if 'google.com' in u else 'Apple' if 'icloud.com' in u else 'agenda'
                try:
                    texto = baixar(u)
                    for k, v in ler_ics(texto, ini, fim).items():
                        ev.setdefault(k, []).extend(v)
                except Exception as e:
                    erros.append('%s: %s' % (nome, str(e)[:120]))
                    print('agenda:', nome, e, file=sys.stderr)
            ICS_CACHE.update(t=time.time() if not erros else time.time() - 840, ev=ev, erros=erros)
        ev = ICS_CACHE['ev']
        fonte = 'ICS ao vivo' + (' · falhou ' + '; '.join(ICS_CACHE.get('erros') or []) if ICS_CACHE.get('erros') else '')
    else:
        snap = ler_json(os.path.join(VAULT, '00_Sistema', 'agenda.json'), {})
        ev, fonte = snap.get('eventos', {}), 'retrato de ' + snap.get('atualizado', '?')
    for d in ev.values():
        d.sort(key=lambda e: (e[0] != 'dia todo', e[0]))
    return ev, fonte


# ---------------------------------------------------------------- montagem
def dados():
    hoje = date.today()
    tk = tarefas(hoje)
    fed = federacao()
    try:
        fed.append(rotinas_saude())
    except Exception as e:
        print('rotinas:', e, file=sys.stderr)
    ev, fonte_ag = agenda(hoje)
    marcos = []
    for m in ler_json(os.path.join(VAULT, '00_Sistema', 'marcos.json'), {}).get('marcos', []):
        try:
            dias = (date.fromisoformat(m['data']) - hoje).days
        except (KeyError, ValueError):
            continue
        if dias >= 0:
            marcos.append(dict(m, dias=dias))
    marcos.sort(key=lambda m: m['dias'])
    for m in marcos:
        ev.setdefault(m['data'], []).insert(0, ['dia todo', m['nome'], 'b'])
    mes_ini = hoje.replace(day=1)
    prox = (mes_ini + timedelta(days=32)).replace(day=1)
    prox_fim = (prox + timedelta(days=32)).replace(day=1)
    ocupados_prox = sum(1 for d, l in ev.items() if prox.isoformat() <= d < prox_fim.isoformat() and any(e[2] == 'b' for e in l))
    return {
        'hoje': hoje.isoformat(), 'agora': datetime.now().strftime('%H:%M'),
        'tarefas': tk, 'federacao': fed, 'eventos': ev, 'agenda_fonte': fonte_ag,
        'ocupados_proximo_mes': ocupados_prox, 'marcos': marcos,
        'treino': ler_json(os.path.join(VAULT, '00_Sistema', 'treino.json'), {}),
        'treino_resumo': _treino_resumo(),
        'emails': emails.carregar(),
        'mesa_home': _mesa_home(),
        'viagem_alertas': _viagem_alertas(),
    }


def concluidas_desde(dia_iso):
    """Tarefas marcadas como feitas (✅ AAAA-MM-DD) a partir da data dada."""
    out = []
    for raiz, _, arqs in os.walk(os.path.join(VAULT, '10_Tarefas')):
        for a in sorted(arqs):
            if a.endswith('.md'):
                for linha in (ler(os.path.join(raiz, a)) or '').splitlines():
                    m = TASK_RE.match(linha)
                    if m and m.group(2).lower() == 'x':
                        dm = re.search(r'✅\s*(\d{4}-\d{2}-\d{2})', m.group(4))
                        if dm and dm.group(1) >= dia_iso:
                            out.append({'titulo': limpar_titulo(m.group(4))[0], 'feita_em': dm.group(1)})
    return out


def _contexto(secoes=None):
    """Retrato do que o Orbitus enxerga, para o Concierge.
    secoes=None manda tudo (rituais e perguntas abertas); senão só o núcleo + os temas pedidos:
    financas, treino, viagem, emails, agenda, tarefas. Menos contexto = resposta mais rápida e mais barata."""
    tudo = secoes is None
    S = set(secoes or ())
    d = dados()
    hoje = date.today()
    lim = (hoje + timedelta(days=14)).isoformat()
    lim_ag = lim if (tudo or 'agenda' in S or 'viagem' in S) else (hoje + timedelta(days=7)).isoformat()
    seg = (hoje - timedelta(days=hoje.weekday())).isoformat()
    c = {'hoje': d['hoje'], 'marcos': d.get('marcos'),
         'tarefas_abertas': [{k: t.get(k) for k in ('titulo', 'due', 'tag', 'nota', 'fonte')} for t in d['tarefas'] if not t.get('feito')],
         'agenda': {k: v for k, v in sorted(d['eventos'].items()) if d['hoje'] <= k <= lim_ag}}
    try:
        ag = rotina.agua_estado(VAULT, d['hoje'])
        c['agua_hoje'] = {k: ag[k] for k in ('bebidos', 'meta', 'esperado', 'atras', 'proximo')}
    except Exception as e:
        c['agua_hoje'] = {'erro': str(e)}
    try:
        dh = dia_ordenado(d['hoje'])
        # revisões/checks do Wealth na agenda não são tarefa dele: quem diz se rodaram é wealth_rotinas_hoje
        _wre = re.compile(r'oportunidade|dividend|provento|sem[aá]foro|carteira|rebalanc|check|revis', re.I)
        c['lista_do_dia'] = [{'hora': x.get('hora'), 'o_que': x.get('texto') + (' (' + x['detalhe'] + ')' if x.get('detalhe') else ''),
                              'tipo': x['tipo'], 'feito': x.get('feito')} for x in dh['itens']
                             if not (x['tipo'] == 'evento' and _wre.search(x.get('texto') or '') and not re.search(r'relat[oó]rio mensal', x.get('texto') or '', re.I))]
        c['wealth_rotinas_hoje'] = [{'rotina': r['nome'], 'estado': r['estado'], 'como': r['texto']} for r in (dh.get('wealth_rotinas') or {}).get('itens', [])]
    except Exception as e:
        c['lista_do_dia'] = {'erro': str(e)}
    if tudo or 'financas' in S:
        c['sistemas'] = [{k: f.get(k) for k in ('nome', 'saude', 'saude_txt', 'proxima', 'risco', 'esperando', 'esperando_lista', 'automacao')} for f in d['federacao']]
    else:
        c['sistemas'] = [{'nome': f.get('nome'), 'saude': f.get('saude')} for f in d['federacao']]
    if tudo or 'tarefas' in S:
        c['tarefas_concluidas_semana'] = concluidas_desde(seg)
    if tudo or 'emails' in S:
        em = d.get('emails') or {}
        c['emails'] = {'configurado': em.get('configurado'), 'contas': em.get('contas'),
                       'pedem_resposta': [{k: e.get(k) for k in ('conta', 'de', 'assunto', 'quando', 'previa')} for e in (em.get('itens') or [])[:15]]}
    else:
        c['emails_pedem_resposta'] = len(((d.get('emails') or {}).get('itens')) or [])
    if tudo or 'financas' in S:
        c['mesa_investimentos'] = d.get('mesa_home')
        try:
            w = wealth.estado(VAULT)
            c['wealth'] = {k: w.get(k) for k in ('data_base', 'total', 'caixa', 'reserva', 'renda_mensal_liq', 'meta_renda', 'meta_patrimonio',
                                                  'modo_preservacao', 'classes', 'bandas', 'alertas', 'decidir', 'isencao', 'proventos_proximos', 'historico')}
            c['wealth']['posicoes'] = [{k: a.get(k) for k in ('ticker', 'classe', 'qtd', 'pm', 'preco', 'valor', 'ganho_pct', 'peso', 'tag')}
                                       for a in (w.get('acoes') or []) + (w.get('fiis') or []) + (w.get('etfs') or [])] + (w.get('outros') or [])
            c['wealth']['agenda'] = [x for x in (w.get('agenda') or []) if (x.get('data') or '') <= lim][:25]
        except Exception as e:
            c['wealth'] = {'erro': str(e)}
    if tudo or 'treino' in S:
        c['treino_resumo'] = d.get('treino_resumo')
        try:
            m = treino.mesa(VAULT)
            c['mesa_da_saude'] = {'ultimo_parecer': (m.get('pareceres') or [None])[0], 'perguntas': (m.get('perguntas') or [])[-5:]}
            t = treino.tudo(VAULT)
            c['treino_ultimos_7_dias'] = {k: {'treino': (v.get('workout') or {}).get('done'), 'passos': v.get('steps'), 'remo_min': v.get('mov'), 'app_saude': v.get('health'),
                                              'agua': v.get('water'), 'peso': v.get('weight'), 'cintura': v.get('waist'),
                                              'refeicoes': {r: (x.get('txt') if isinstance(x, dict) else x) for r, x in (v.get('meals') or {}).items()},
                                              'extras': [x.get('n') for x in v.get('extras') or []]}
                                          for k, v in sorted(t['dias'].items())[-7:]}
            c['locais_de_treino'] = t.get('locais')
        except Exception as e:
            c['mesa_da_saude'] = {'erro': str(e)}
    else:
        tr = d.get('treino_resumo') or {}
        c['treino_hoje'] = {k: tr.get(k) for k in ('data', 'sessao_nome', 'treino_ok', 'treinos_semana', 'treinos_alvo') if k in tr}
    if tudo or 'agenda' in S or 'viagem' in S:
        try:
            ap = agenda_proativa(16)
            c['agenda_radar'] = [r['texto'] + (' ' + r['acao'] if r.get('acao') else '') for r in ap['radar']]
            c['proximos_dias'] = [{'data': x['data'], 'local': x['local'], 'clima': ({k: x['clima'].get(k) for k in ('texto', 'min', 'max', 'chuva')} if x['clima'] else None),
                                   'itens': [(i['hora'] + ' ' if i['hora'] else '') + i['titulo'] for i in x['itens']], 'levar': x['levar']}
                                  for x in ap['dias'][:10] if x['itens'] or x['clima']]
        except Exception as e:
            c['agenda_radar'] = {'erro': str(e)}
    if tudo or 'viagem' in S:
        c['viagem_alertas'] = d.get('viagem_alertas')
        try:
            vs = []
            for v in viagem.listar(VAULT):
                e = viagem.estado(VAULT, v['id'])
                vs.append({'titulo': e.get('titulo'), 'de': e.get('de'), 'ate': e.get('ate'),
                           'paradas': [{k: p.get(k) for k in ('nome', 'de', 'ate', 'hora', 'nota')} for p in e.get('paradas', [])],
                           'falta_antes_de_ir': (e.get('vespera') or {}).get('falta'), 'bagagem': e.get('bagagem'),
                           'lista_aberta': [i['titulo'] + (' (' + i['due'] + ')' if i['due'] else '') for i in e.get('lista', []) if not i['feito']]})
            c['viagens'] = vs
        except Exception as e:
            c['viagens'] = {'erro': str(e)}
    return c


def rotinas_saude():
    """Saúde das rotinas do próprio Orbitus: cada uma deixa um rastro no cofre; rastro velho = vermelho."""
    agora = datetime.now()
    hoje, ontem = date.today().isoformat(), (date.today() - timedelta(days=1)).isoformat()
    falhas, avisos, ok = [], [], []

    def esperado(hora, minuto):   # dia da última execução que já deveria ter acontecido
        return hoje if (agora.hour, agora.minute) >= (hora, minuto) else ontem

    # backup do cofre (23:17)
    b = ler_json(os.path.join(VAULT, '00_Sistema', 'rotinas', 'backup.json'), None)
    if not b:
        avisos.append('Backup do cofre ainda não instalado')
    else:
        dia = (b.get('quando') or '')[:10]
        if b.get('status') == 'falha':
            falhas.append('Backup do cofre falhou: ' + (b.get('detalhe') or '')[:120])
        elif dia < esperado(23, 40):
            falhas.append('Backup do cofre não rodou desde ' + (dia or '?'))
        elif b.get('status') == 'atencao':
            avisos.append('Backup: ' + (b.get('detalhe') or '')[:120])
        else:
            ok.append('backup')
    # Mesa da Saúde (21:47) grava pareceres/AAAA-MM-DD.json
    pd = os.path.join(VAULT, '20_Treino', 'Mesa da Saúde', 'pareceres')
    ult = max([n[:10] for n in os.listdir(pd) if n.endswith('.json')], default='') if os.path.isdir(pd) else ''
    if hoje >= '2026-10-31':
        if ult < esperado(22, 20):
            falhas.append('Mesa da Saúde não deu parecer desde ' + (ult or '?'))
        else:
            ok.append('mesa da saúde')
    # Radar da bagagem (07:47) grava bagagem.radar.data no roteiro de Praia do Forte
    rot = ler_json(os.path.join(VAULT, '30_Viagens', 'Praia do Forte 2026', 'roteiro.json'), {})
    bg = rot.get('bagagem') or {}
    if bg and not bg.get('comprada') and hoje <= '2026-12-24' and hoje >= '2026-10-31':
        rd = (bg.get('radar') or {}).get('data', '')
        if rd < esperado(8, 20):
            falhas.append('Radar da bagagem GOL não rodou desde ' + (rd or '?'))
        else:
            ok.append('radar GOL')
    # Lembretes (13:37 e 20:37) gravam 00_Sistema/rotinas/lembretes.json
    lb = ler_json(os.path.join(VAULT, '00_Sistema', 'rotinas', 'lembretes.json'), None)
    if not lb:
        avisos.append('Lembretes de treino: ainda sem sinal')
    else:
        q = lb.get('quando') or ''
        lim = hoje + 'T13:37' if agora.hour * 60 + agora.minute >= 14 * 60 + 5 else ontem + 'T20:37'
        if (agora.hour * 60 + agora.minute) >= 21 * 60 + 5:
            lim = hoje + 'T20:37'
        if q < lim:
            falhas.append('Lembretes de treino não rodam desde ' + (q[:16].replace('T', ' ') or '?'))
        else:
            ok.append('lembretes')
    # Sentinela do Wealth (10:37 e 22:37) grava 00_Sistema/rotinas/sentinela_wealth.json.
    # Aqui só conta se ela está viva; o conteúdo (atenção do Wealth) já aparece no card do Wealth.
    sw = ler_json(os.path.join(VAULT, '00_Sistema', 'rotinas', 'sentinela_wealth.json'), None)
    if hoje >= '2026-11-02':
        if not sw:
            avisos.append('Sentinela do Wealth: ainda sem sinal')
        else:
            q = sw.get('quando') or ''
            m = agora.hour * 60 + agora.minute
            lim = hoje + 'T22:37' if m >= 23 * 60 + 20 else hoje + 'T10:37' if m >= 11 * 60 + 20 else ontem + 'T22:37'
            if q < lim:
                falhas.append('Sentinela do Wealth não roda desde ' + (q[:16].replace('T', ' ') or '?'))
            elif sw.get('status') == 'falha':
                falhas.append('Sentinela achou rotina do Wealth parada: ' + (sw.get('detalhe') or '')[:120])
            else:
                ok.append('sentinela do Wealth')
    # Lente (UX/UI): quarta 09:23 grava 00_Sistema/rotinas/lente.json (a partir de 11/11)
    if hoje >= '2026-11-11':
        ln = ler_json(os.path.join(VAULT, '00_Sistema', 'rotinas', 'lente.json'), None) or {}
        qua = date.today() - timedelta(days=(date.today().weekday() - 2) % 7)
        if qua == date.today() and (agora.hour, agora.minute) < (10, 30):
            qua -= timedelta(days=7)
        if (ln.get('quando') or '')[:10] < qua.isoformat():
            falhas.append('Lente não avaliou desde ' + ((ln.get('quando') or '?')[:10]))
        else:
            ok.append('lente')
    saude = '🔴' if falhas else '🟡' if avisos else '🟢'
    txt = ('vermelho' if falhas else 'amarelo' if avisos else 'verde') + '. ' + (
        'Em dia: ' + ', '.join(ok) + '.' if ok else '') + ((' Atenção: ' + '; '.join(avisos) + '.') if avisos else '')
    return {'id': 'orbitus', 'nome': 'Rotinas do Orbitus', 'icone': '🛰️', 'saude': saude, 'saude_txt': txt.strip(),
            'falhas': falhas, 'esperando': '', 'esperando_lista': avisos,
            'proxima': 'Mac ligado e app do Claude aberto às 07:47, 10:37, 13:37, 20:37, 21:47, 22:37 e 23:17',
            'automacao': '%d falha(s) · %d atenção(ões)' % (len(falhas), len(avisos))}


def _treino_resumo():
    try:
        return treino.resumo(VAULT)
    except Exception as e:
        print('treino: resumo falhou:', e, file=sys.stderr)
        return {}


def _viagem_alertas():
    try:
        return viagem.alertas(VAULT)
    except Exception as e:
        print('viagem: alertas falharam:', e, file=sys.stderr)
        return []


def _mesa_home():
    try:
        e = mesa.estado(VAULT)
    except Exception as ex:
        return {'erro': str(ex)}
    if not e.get('disponivel'):
        return {'disponivel': False}
    hoje = date.today().isoformat()
    abertas = [d for d in e['decisoes'] if d.get('status') == 'aberta']
    prox = sorted([p for p in e['plano'] if p.get('status') == 'pendente' and p.get('quem') == 'voce'
                   and ('plano:' + p['id']) not in e['respostas']],
                  key=lambda p: p.get('inicio') or '9999')[:3]
    lanc = [l for l in e['lancamentos'] if l.get('status') == 'aguardando']
    return {'disponivel': True, 'abertas': abertas, 'respostas': e['respostas'], 'proximos_passos': prox,
            'lancamentos_aguardando': len(lanc), 'hoje': hoje}


USO_CAMPOS = {'em': str, 'ev': str, 'aba': str, 'alvo': str, 'x': (int, float), 'y': (int, float),
              'vw': (int, float), 'vh': (int, float), 'morto': bool, 'raiva': (int, float), 'seg': (int, float)}


def uso_gravar(body):
    """Eventos de uso para o Lente e o mapa de calor: só posição, elemento e aba (nunca texto)."""
    evs = body.get('eventos') if isinstance(body, dict) else None
    if not isinstance(evs, list):
        return {'ok': False}
    linhas = []
    for e in evs[:200]:
        if not isinstance(e, dict) or e.get('ev') not in ('clique', 'aba', 'tempo'):
            continue
        d = {k: (v[:120] if isinstance(v, str) else v) for k, v in e.items() if k in USO_CAMPOS and isinstance(v, USO_CAMPOS[k])}
        if not re.fullmatch(r'[a-z0-9_-]{1,20}', d.get('aba', '')):
            continue
        d['em'] = datetime.now().isoformat(timespec='seconds')   # hora do Mac, não do navegador
        linhas.append(json.dumps(d, ensure_ascii=False))
    if linhas:
        pasta = os.path.join(VAULT, '00_Sistema', 'uso')
        os.makedirs(pasta, exist_ok=True)
        with LOCK:
            with open(os.path.join(pasta, date.today().strftime('%Y-%m') + '.jsonl'), 'a', encoding='utf-8') as f:
                f.write('\n'.join(linhas) + '\n')
    return {'ok': True, 'gravados': len(linhas)}


def uso_resumo():
    """Para o Lente na sala 3D: cliques de hoje, cliques sem efeito e os pontos da Home (sem texto)."""
    hoje = date.today().isoformat()
    evs = [e for e in uso_ler('?dias=1')['eventos'] if (e.get('em') or '')[:10] == hoje]
    cl = [e for e in evs if e.get('ev') == 'clique']
    pts = [[e.get('x', 0), min(1.0, round((e.get('y') or 0) / 1300, 3)), 1 if e.get('morto') else 0]
           for e in cl if e.get('aba') == 'home'][-300:]
    pasta = os.path.join(VAULT, '00_Sistema', 'lente')
    av = sorted(n[:10] for n in os.listdir(pasta) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.md', n)) if os.path.isdir(pasta) else []
    return {'cliques': len(cl), 'mortos': sum(1 for e in cl if e.get('morto')), 'raiva': sum(1 for e in cl if e.get('raiva')),
            'abas': len({e.get('aba') for e in evs if e.get('aba')}), 'pontos': pts, 'ultima_avaliacao': av[-1] if av else None}


def uso_ler(caminho):
    m = re.search(r'[?&]dias=(\d+)', caminho)
    dias = min(int(m.group(1)) if m else 30, 120)
    corte = (datetime.now() - timedelta(days=dias)).isoformat(timespec='seconds')
    pasta, out = os.path.join(VAULT, '00_Sistema', 'uso'), []
    if os.path.isdir(pasta):
        for n in sorted(os.listdir(pasta))[-5:]:
            for l in (ler(os.path.join(pasta, n)) or '').splitlines():
                try:
                    e = json.loads(l)
                except ValueError:
                    continue
                if e.get('em', '') >= corte:
                    out.append(e)
    return {'eventos': out[-20000:]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _fluxo(self, gerador):
        """Server-sent events: cada pedaço da resposta sai assim que chega da API (a voz começa na primeira frase)."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Accel-Buffering', 'no')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True

        def env(obj):
            self.wfile.write(('data: ' + json.dumps(obj, ensure_ascii=False) + '\n\n').encode('utf-8'))
            self.wfile.flush()
        try:
            for ev in gerador:
                env(ev)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as e:
            try:
                env({'t': 'erro', 'erro': str(e)})
            except OSError:
                pass

    def do_GET(self):
        if self.path.split('?')[0] in ('/', '/index.html'):
            b = (ler(os.path.join(STATIC, 'index.html')) or '').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.split('?')[0] == '/manifest.webmanifest':
            b = json.dumps({'name': 'Orbitus', 'short_name': 'Orbitus', 'start_url': '/', 'display': 'standalone',
                            'background_color': '#04060b', 'theme_color': '#04060b',
                            'icons': [{'src': '/static/icone-192.png', 'sizes': '192x192', 'type': 'image/png'},
                                      {'src': '/static/icone-512.png', 'sizes': '512x512', 'type': 'image/png'}]}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/manifest+json')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif re.fullmatch(r'/static/icone-(180|192|512)\.png', self.path.split('?')[0]):
            try:
                with open(os.path.join(STATIC, self.path.split('?')[0][8:]), 'rb') as f:
                    b = f.read()
            except OSError:
                return self.send_error(404)
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Cache-Control', 'max-age=86400')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif re.fullmatch(r'/static/rosto/[a-z0-9_]+\.(js|json)', self.path.split('?')[0]):
            # rosto 3D da Vega: módulo e malha (só estes dois tipos, só desta pasta)
            nome = self.path.split('?')[0][len('/static/rosto/'):]
            try:
                with open(os.path.join(STATIC, 'rosto', nome), 'rb') as f:
                    b = f.read()
            except OSError:
                return self.send_error(404)
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8' if nome.endswith('.js') else 'application/json')
            self.send_header('Cache-Control', 'no-cache' if nome.endswith('.js') else 'max-age=604800')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.split('?')[0] in ('/static/uso.js', '/static/demo.js'):
            b = (ler(os.path.join(STATIC, self.path.split('?')[0][8:])) or '').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.split('?')[0] == '/api/uso':
            self._json(uso_resumo() if 'resumo=1' in self.path else uso_ler(self.path))
        elif self.path.split('?')[0] == '/sw.js':
            b = (ler(os.path.join(STATIC, 'sw.js')) or '').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.send_header('Service-Worker-Allowed', '/')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.split('?')[0] == '/api/push':
            self._json(push.estado())
        elif self.path.split('?')[0] == '/treino.html':
            b = (ler(os.path.join(STATIC, 'treino.html')) or '').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.split('?')[0] == '/api/tarefas/entender':
            t = parse_qs(urlparse(self.path).query).get('t', [''])[0][:400]
            self._json(tarefas_api.interpretar(t))
        elif self.path.split('?')[0] == '/api/tarefas':
            try:
                h = tarefas_api.historico(VAULT)
                h['sugestoes'] = _sugestoes()
                for k in ('feitas', 'arquivo'):
                    h[k] = [{c: t.get(c) for c in ('titulo', 'fonte', 'area', 'due', 'hora', 'feita_em', 'removida_em', 'arquivo', 'linha', 'texto', 'repete')} for t in h[k]]
                self._json(h)
            except Exception as e:
                self._json({'erro': str(e)}, 500)
        elif self.path.split('?')[0] == '/api/agenda':
            try:
                n = int(parse_qs(urlparse(self.path).query).get('dias', ['45'])[0])
                self._json(agenda_proativa(max(7, min(90, n))))
            except Exception as e:
                self._json({'erro': str(e)}, 500)
        elif self.path.split('?')[0] == '/api/dia':
            d = parse_qs(urlparse(self.path).query).get('d', [date.today().isoformat()])[0]
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', d):
                return self._json({'erro': 'data inválida'}, 400)
            try:
                self._json(dia_ordenado(d))
            except Exception as e:
                self._json({'erro': str(e)}, 500)
        elif self.path.split('?')[0] == '/api/sistema':
            # página "Saúde do sistema": onde ficam os erros técnicos (fora da Home)
            try:
                w = mesa.pasta_wealth(VAULT)
                rot = []
                pr = os.path.join(VAULT, '00_Sistema', 'rotinas')
                for n in sorted(os.listdir(pr)) if os.path.isdir(pr) else []:
                    if n.endswith('.json'):
                        j = ler_json(os.path.join(pr, n), None)
                        if isinstance(j, dict):
                            rot.append({k: j.get(k) for k in ('rotina', 'quando', 'status', 'detalhe')})
                rl = (ler(os.path.join(VAULT, '00_Sistema', 'reinicio.log')) or '').strip().splitlines()[-8:]
                return self._json({'wealth_hoje': wealth_rotinas.do_dia(w, date.today()),
                                   'wealth_ontem': wealth_rotinas.do_dia(w, date.today() - timedelta(days=1), datetime.now()),
                                   'saude_wealth': wealth_rotinas.status_automacao(w), 'orbitus': rot, 'reinicios': rl})
            except Exception as e:
                return self._json({'erro': str(e)}, 500)
        elif self.path.split('?')[0] == '/api/concierge':
            self._json(concierge.estado())
        elif self.path.split('?')[0] == '/api/voz/amostra':
            nome = re.sub(r'[^A-Za-z0-9-]', '', parse_qs(urlparse(self.path).query).get('v', ['Aoede'])[0])[:40] or 'Aoede'
            try:
                b, tipo = concierge._google_tts('Boa noite, Marcio. Você está em sete de dez copos de água, o que para um domingo é quase heroico. Praia do Forte está chegando, e a mala, como sempre, vai ser feita na véspera.', 'google:pt-BR-Chirp3-HD-' + nome)
            except RuntimeError as e:
                return self._json({'erro': str(e)}, 400)
            self.send_response(200)
            self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.split('?')[0] == '/api/voz':
            self._json({'voz': concierge.voz_escolhida(), 'disponiveis': concierge.vozes(), 'tom': concierge.cfg().get('tom', 'espirituoso'),
                        'sugeridas': [{'nome': n, 'desc': d} for n, d in concierge.VOZES_SUGERIDAS]})
        elif self.path.split('?')[0] == '/api/treino':
            try:
                self._json(treino.tudo(VAULT))
            except Exception as e:
                self._json({'erro': str(e)}, 500)
        elif self.path.startswith('/static/') and re.fullmatch(r'/static/[a-z0-9_\-]+\.json', self.path.split('?')[0]):
            b = (ler(os.path.join(STATIC, self.path.split('?')[0][8:])) or '').encode('utf-8')
            if not b:
                return self.send_error(404)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.startswith('/api/viagem/arquivo'):
            q = parse_qs(urlparse(self.path).query)
            try:
                b, tipo = viagem.arquivo(VAULT, q.get('v', [''])[0], q.get('f', [''])[0])
            except (OSError, ValueError):
                return self.send_error(404)
            self.send_response(200)
            self.send_header('Content-Type', tipo)
            self.send_header('Content-Disposition', 'inline')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', 'sandbox')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.startswith('/api/viagem'):
            try:
                self._json(viagem.estado(VAULT, parse_qs(urlparse(self.path).query).get('v', [None])[0]))
            except Exception as e:
                self._json({'erro': str(e)}, 500)
        elif self.path.startswith('/api/wealth'):
            try:
                self._json(wealth.estado(VAULT))
            except Exception as e:
                self._json({'erro': str(e)}, 500)
        elif self.path.startswith('/api/mesa'):
            try:
                self._json(mesa.estado(VAULT))
            except Exception as e:
                self._json({'erro': str(e)}, 500)
        elif self.path.startswith('/api/dados'):
            try:
                self._json(dados())
            except Exception as e:
                self._json({'erro': str(e)}, 500)
        else:
            self.send_error(404)

    def do_POST(self):
        o = self.headers.get('Origin')
        # celular via Tailscale Serve: https://<mac>.<tailnet>.ts.net (só os aparelhos da sua rede Tailscale chegam aqui)
        ts = bool(o and re.fullmatch(r'https://[a-z0-9-]+\.[a-z0-9-]+\.ts\.net', o))
        if o not in (None, 'http://localhost:%d' % PORT, 'http://127.0.0.1:%d' % PORT) and not ts:
            return self._json({'erro': 'origem recusada'}, 403)
        try:
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(min(n, 3500000 if self.path == '/api/voz/transcrever' else 400000)) or b'{}')
            if self.path == '/api/alternar':
                nova, n, prox = alternar(body['arquivo'], int(body['linha']), body['texto'])
                return self._json({'ok': True, 'texto': nova, 'linha': n, 'proxima': prox})
            elif self.path == '/api/capturar':
                capturar(body.get('texto', ''))
            elif self.path == '/api/treino/dia':
                return self._json(treino.salvar_dia(VAULT, body))
            elif self.path == '/api/treino/despensa':
                return self._json(treino.salvar_despensa(VAULT, body))
            elif self.path == '/api/concierge':
                try:
                    sec = concierge.intencoes(body.get('pergunta'))
                    return self._json(concierge.perguntar(body.get('pergunta'), _contexto(sec), capturar, sec))
                except RuntimeError as e:
                    return self._json({'erro': str(e)}, 502)
            elif self.path == '/api/cio':
                chave = concierge._chave()
                if not chave:
                    raise ValueError('chave da API não configurada')
                u = concierge._uso()
                if u['usd'] >= u.get('teto', concierge.TETO_PADRAO):
                    raise ValueError('teto do mês atingido (US$ %.2f)' % u.get('teto', concierge.TETO_PADRAO))
                try:
                    w = wealth.estado(VAULT)
                except Exception:
                    w = {}
                prep = cio.preparar(body.get('pergunta'), mesa.pasta_wealth(VAULT), w, concierge.MODELO, chave)
                return self._fluxo(_cio_fluxo(prep))
            elif self.path == '/api/cio/nova':
                return self._json(cio.nova())
            elif self.path == '/api/cio/1on1':
                return self._json(cio.levar_ao_1on1(mesa.pasta_wealth(VAULT), body))
            elif self.path == '/api/concierge/fluxo':
                sec = concierge.intencoes(body.get('pergunta'))
                prep = concierge.preparar(body.get('pergunta'), _contexto(sec), sec)
                return self._fluxo(concierge.perguntar_fluxo(prep, capturar))
            elif self.path == '/api/tarefas/criar':
                return self._json(tarefas_api.criar(VAULT, body))
            elif self.path == '/api/tarefas/editar':
                return self._json(tarefas_api.editar(VAULT, body))
            elif self.path == '/api/tarefas/remover':
                return self._json(tarefas_api.remover(VAULT, body))
            elif self.path == '/api/tarefas/restaurar':
                return self._json(tarefas_api.restaurar(VAULT, body))
            elif self.path == '/api/tarefas/rapida':
                # Siri, menu Compartilhar e o campo de captura: entende "sexta 10h", "amanhã", "todo dia", "urgente"
                f = tarefas_api.interpretar(body.get('texto') or '')
                u = str(body.get('url') or '').strip()
                if u and not f['url'] and re.match(r'^https?://\S+$', u):
                    f['url'] = u
                if not f['titulo'] and f['url']:
                    f['titulo'] = 'Ver ' + re.sub(r'^https?://(www\.)?', '', f['url']).split('/')[0]
                if body.get('dia') and not f['due']:
                    f['due'] = str(body['dia'])[:10]
                for k in ('due', 'hora', 'area', 'prio', 'repete', 'status'):
                    if body.get(k) not in (None, ''):
                        f[k] = body[k]
                r = tarefas_api.criar(VAULT, f)
                fala = 'Anotado: ' + r['resumo'] + '.'
                # aniversário, casamento…: cria a tarefa do presente e confere a agenda do dia
                r['extras'] = []
                abertas = [tarefas_api._palavras(t['titulo']) for t in tarefas_api._todas(VAULT) if not t['feito'] and not t['cancelada']]
                for x in tarefas_api.tarefas_do_evento(f):
                    if tarefas_api._parecida(x['titulo'], abertas):
                        continue
                    try:
                        tarefas_api.criar(VAULT, x)
                        r['extras'].append(tarefas_api.resumo(dict(x, hora='', repete='')))
                    except Exception as e:
                        print('evento: presente falhou', e, file=sys.stderr)
                r['conflitos'] = []
                if f.get('due'):
                    try:
                        ev = (agenda(date.today())[0] or {}).get(f['due'], [])
                        r['conflitos'] = tarefas_api.conflitos(f['due'], f.get('hora'), ev, tarefas_do_dia(f['due']), f['titulo'])
                    except Exception as e:
                        print('evento: conflito falhou', e, file=sys.stderr)
                if r['extras']:
                    fala += ' Criei também: ' + '; '.join(r['extras']) + '.'
                if r['conflitos']:
                    fala += ' Atenção, nesse dia já tem: ' + '; '.join(c['hora'] + ' ' + c['texto'] for c in r['conflitos'][:3]) + '.'
                r['due'] = f.get('due', '')
                r['falar'] = fala
                return self._json(r)
            elif self.path == '/api/tarefas/sugestao':
                return self._json(tarefas_api.responder_sugestao(VAULT, body, _sugestoes()))
            elif self.path == '/api/uso':
                return self._json(uso_gravar(body))
            elif self.path == '/api/diag':
                linha = json.dumps({'em': datetime.now().isoformat(timespec='seconds'), 'ev': str(body.get('ev'))[:30], 'det': str(body.get('det'))[:80],
                                    'ua': str(body.get('ua'))[:140], 'app': bool(body.get('sa'))}, ensure_ascii=False)
                pd_ = os.path.join(VAULT, '00_Sistema', 'diagnostico.jsonl')
                with LOCK:
                    ls = ((ler(pd_) or '').splitlines() + [linha])[-300:]
                    with open(pd_, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(ls) + '\n')
                return self._json({'ok': True})
            elif self.path == '/api/push/inscrever':
                return self._json(push.inscrever(body))
            elif self.path == '/api/push/teste':
                try:
                    return self._json(push.enviar('Orbitus', 'Avisos ligados. Água e tarefas com hora chegam aqui.', 'teste', '/'))
                except RuntimeError as e:
                    return self._json({'erro': str(e)}, 400)
            elif self.path == '/api/agua':
                return self._json(rotina.agua_somar(VAULT, str(body.get('dia') or date.today().isoformat())[:10], body.get('delta', 1)))
            elif self.path == '/api/dia/marcar':
                return self._json(rotina.marcar(VAULT, body))
            elif self.path == '/api/dia/adicionar':
                d = str(body.get('dia') or date.today().isoformat())[:10]
                t = re.sub(r'\s+', ' ', str(body.get('texto') or '')).strip()
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', d) or not t:
                    raise ValueError('escreva o que fazer')
                m = re.match(r'^(\d{1,2})[:h](\d{2})\s+(.+)$', t)
                hora, t = (('%02d:%s' % (int(m.group(1)), m.group(2))), m.group(3)) if m else (str(body.get('hora') or '')[:5], t)
                capturar(t + ' 📅 ' + d + (' ⏰ ' + hora if re.match(r'^\d{2}:\d{2}$', hora or '') else ''))
                return self._json({'ok': True})
            elif self.path == '/api/treino/saude':
                return self._json(treino.registrar_saude(VAULT, body))
            elif self.path == '/api/diario/entender':
                d = str(body.get('dia') or date.today().isoformat())[:10]
                return self._json(diario.entender(VAULT, body.get('texto'), d, dia_ordenado(d).get('itens', []), 140))
            elif self.path == '/api/diario/aplicar':
                return self._json(diario.aplicar(VAULT, body, alternar, capturar))
            elif self.path == '/api/diario/desfazer':
                return self._json(diario.desfazer(VAULT, body.get('id')))
            elif self.path == '/api/voz/transcrever':
                return self._json(diario.transcrever(body))
            elif self.path == '/api/voz/escolher':
                return self._json(concierge.escolher_voz(body))
            elif self.path == '/api/voz':
                try:
                    b, tipo = concierge.sintetizar(body.get('texto'))
                except (RuntimeError, ValueError) as e:
                    return self._json({'erro': str(e)}, 400)
                self.send_response(200)
                self.send_header('Content-Type', tipo)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            elif self.path == '/api/concierge/nova':
                return self._json(concierge.nova_conversa())
            elif self.path == '/api/treino/pergunta':
                return self._json(treino.perguntar(VAULT, body))
            elif self.path == '/api/treino/resumo':
                return self._json(treino.salvar_resumo(VAULT, body))
            elif self.path == '/api/viagem/lista':
                viagem.editar(VAULT, body)
            elif self.path == '/api/mesa/responder':
                return self._json({'ok': True, 'resposta': mesa.responder(VAULT, body)})
            else:
                return self.send_error(404)
            self._json({'ok': True})
        except (ValueError, KeyError) as e:
            self._json({'erro': str(e)}, 400)



def _marcas_codigo():
    import glob
    return {f: os.path.getmtime(f) for f in glob.glob(os.path.join(APP, '*.py'))}


def _anotar_reinicio(txt):
    try:
        with open(os.path.join(VAULT, '00_Sistema', 'reinicio.log'), 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (datetime.now().isoformat(timespec='seconds'), txt))
    except OSError:
        pass


def vigia_codigo():
    """Aplica código novo sozinho (fim do kickstart manual). Quando um .py do App muda, confere num processo à parte
    se tudo compila e importa; se estiver bom, encerra e o launchd (KeepAlive) sobe o servidor de novo com o código novo.
    Se estiver quebrado, segue rodando o código antigo e anota o erro em 00_Sistema/reinicio.log."""
    import subprocess
    base = _marcas_codigo()
    while True:
        time.sleep(5)
        try:
            agora = _marcas_codigo()
            if agora == base:
                continue
            time.sleep(4)                       # espera a cópia dos arquivos terminar
            agora = _marcas_codigo()
            mods = ['server']                   # importar o server puxa todos os módulos que ele usa (o __main__ não roda)
            prova = ('import sys, glob, py_compile; sys.path.insert(0, %r); '
                     '[py_compile.compile(f, doraise=True) for f in glob.glob(%r)]; ' % (APP, os.path.join(APP, '*.py'))
                     + '; '.join('import ' + m for m in mods))
            r = subprocess.run([sys.executable, '-c', prova], capture_output=True, text=True, timeout=90, cwd=APP)
            mudou = ', '.join(sorted(os.path.basename(f) for f in agora if agora.get(f) != base.get(f)))
            if r.returncode == 0:
                _anotar_reinicio('código novo (%s) conferido: reiniciando' % mudou)
                os._exit(0)
            _anotar_reinicio('código novo (%s) NÃO aplicado, segue o antigo: %s' % (mudou, (r.stderr or r.stdout).strip().splitlines()[-1:]))
            base = agora
        except Exception as e:
            _anotar_reinicio('vigia: ' + str(e)[:200])
            base = _marcas_codigo()

if __name__ == '__main__':
    print('Orbitus em http://localhost:%d  (cofre: %s)' % (PORT, VAULT))
    threading.Thread(target=push.ciclo, args=(dia_ordenado,), daemon=True).start()
    threading.Thread(target=vigia_codigo, daemon=True).start()
    _anotar_reinicio('servidor no ar (pid %d)' % os.getpid())
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
