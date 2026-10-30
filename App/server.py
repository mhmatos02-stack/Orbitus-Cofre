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
import mesa
import wealth
import viagem
import treino
import concierge

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
                low = corpo.lower()
                tag = 'Finanças' if any(t in low for t in FIN_TAGS) else 'Pessoal'
                titulo, fonte = limpar_titulo(corpo)
                if due and due <= hoje.isoformat() or prio == 0:
                    col = 'hoje'
                elif due and due <= (hoje + timedelta(days=7)).isoformat():
                    col = 'semana'
                else:
                    col = 'depois'
                out.append({'arquivo': rel, 'linha': i, 'texto': linha, 'titulo': titulo, 'fonte': fonte,
                            'tag': tag, 'due': due, 'prio': prio, 'feito': feito, 'col': col,
                            'atrasada': bool(due and due < hoje.isoformat() and not feito)})
    out.sort(key=lambda t: (t['feito'], t['prio'], t['due'] or '9999'))
    return out


def alternar(arquivo, linha, texto):
    p = os.path.normpath(os.path.join(VAULT, arquivo))
    if not p.startswith(os.path.join(VAULT, '10_Tarefas')) or not p.endswith('.md'):
        raise ValueError('arquivo fora de 10_Tarefas')
    with LOCK:
        linhas = (ler(p) or '').split('\n')
        if linha >= len(linhas) or linhas[linha] != texto:
            raise ValueError('a tarefa mudou no Obsidian; recarregue o painel')
        m = TASK_RE.match(linhas[linha])
        if m.group(2) == ' ':
            nova = m.group(1) + 'x' + m.group(3) + m.group(4).rstrip() + ' ✅ ' + date.today().isoformat()
        else:
            nova = m.group(1) + ' ' + m.group(3) + DONE_RE.sub('', m.group(4)).rstrip()
        linhas[linha] = nova
        with open(p, 'w', encoding='utf-8') as f:
            f.write('\n'.join(linhas))
        return nova


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


def _contexto():
    """Retrato compacto de tudo o que o Orbitus enxerga, para o Concierge."""
    d = dados()
    hoje = date.today()
    lim = (hoje + timedelta(days=14)).isoformat()
    seg = (hoje - timedelta(days=hoje.weekday())).isoformat()
    c = {'hoje': d['hoje'], 'marcos': d.get('marcos'),
         'tarefas_concluidas_semana': concluidas_desde(seg),
         'tarefas_abertas': [{k: t.get(k) for k in ('titulo', 'due', 'tag', 'nota', 'fonte')} for t in d['tarefas'] if not t.get('feito')],
         'agenda_14_dias': {k: v for k, v in sorted(d['eventos'].items()) if d['hoje'] <= k <= lim},
         'sistemas': [{k: f.get(k) for k in ('nome', 'saude', 'saude_txt', 'proxima', 'risco', 'esperando', 'esperando_lista', 'automacao')} for f in d['federacao']],
         'mesa_investimentos': d.get('mesa_home'), 'viagem_alertas': d.get('viagem_alertas'),
         'treino_resumo': d.get('treino_resumo')}
    em = d.get('emails') or {}
    c['emails'] = {'configurado': em.get('configurado'), 'contas': em.get('contas'),
                   'pedem_resposta': [{k: e.get(k) for k in ('conta', 'de', 'assunto', 'quando', 'previa')} for e in (em.get('itens') or [])[:15]]}
    try:
        w = wealth.estado(VAULT)
        c['wealth'] = {k: w.get(k) for k in ('data_base', 'total', 'caixa', 'reserva', 'renda_mensal_liq', 'meta_renda', 'meta_patrimonio',
                                              'modo_preservacao', 'classes', 'bandas', 'alertas', 'decidir', 'isencao', 'proventos_proximos', 'historico')}
        c['wealth']['posicoes'] = [{k: a.get(k) for k in ('ticker', 'classe', 'qtd', 'pm', 'preco', 'valor', 'ganho_pct', 'peso', 'tag')}
                                   for a in (w.get('acoes') or []) + (w.get('fiis') or []) + (w.get('etfs') or [])] + (w.get('outros') or [])
        c['wealth']['agenda'] = [x for x in (w.get('agenda') or []) if (x.get('data') or '') <= lim][:25]
    except Exception as e:
        c['wealth'] = {'erro': str(e)}
    try:
        m = treino.mesa(VAULT)
        c['mesa_da_saude'] = {'ultimo_parecer': (m.get('pareceres') or [None])[0], 'perguntas': (m.get('perguntas') or [])[-5:]}
        t = treino.tudo(VAULT)
        c['treino_ultimos_7_dias'] = {k: {'treino': (v.get('workout') or {}).get('done'), 'passos': v.get('steps'), 'remo_min': v.get('mov'),
                                          'agua': v.get('water'), 'peso': v.get('weight'), 'cintura': v.get('waist'),
                                          'refeicoes': {r: (x.get('txt') if isinstance(x, dict) else x) for r, x in (v.get('meals') or {}).items()},
                                          'extras': [x.get('n') for x in v.get('extras') or []]}
                                      for k, v in sorted(t['dias'].items())[-7:]}
        c['locais_de_treino'] = t.get('locais')
    except Exception as e:
        c['mesa_da_saude'] = {'erro': str(e)}
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
    saude = '🔴' if falhas else '🟡' if avisos else '🟢'
    txt = ('vermelho' if falhas else 'amarelo' if avisos else 'verde') + '. ' + (
        'Em dia: ' + ', '.join(ok) + '.' if ok else '') + ((' Atenção: ' + '; '.join(avisos) + '.') if avisos else '')
    return {'id': 'orbitus', 'nome': 'Rotinas do Orbitus', 'icone': '🛰️', 'saude': saude, 'saude_txt': txt.strip(),
            'falhas': falhas, 'esperando': '', 'esperando_lista': avisos,
            'proxima': 'Mac ligado e app do Claude aberto às 07:47, 13:37, 20:37, 21:47 e 23:17',
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

    def do_GET(self):
        if self.path.split('?')[0] in ('/', '/index.html'):
            b = (ler(os.path.join(STATIC, 'index.html')) or '').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.split('?')[0] == '/treino.html':
            b = (ler(os.path.join(STATIC, 'treino.html')) or '').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.split('?')[0] == '/api/concierge':
            self._json(concierge.estado())
        elif self.path.split('?')[0] == '/api/voz/amostra':
            nome = re.sub(r'[^A-Za-z0-9-]', '', parse_qs(urlparse(self.path).query).get('v', ['Aoede'])[0])[:40] or 'Aoede'
            try:
                b, tipo = concierge._google_tts('Olá, Marcio. Eu sou o Orbitus. Faltam quarenta e três dias para Praia do Forte, e hoje você tem três tarefas na semana.', 'google:pt-BR-Chirp3-HD-' + nome)
            except RuntimeError as e:
                return self._json({'erro': str(e)}, 400)
            self.send_response(200)
            self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.split('?')[0] == '/api/voz':
            self._json({'voz': concierge.voz_escolhida(), 'disponiveis': concierge.vozes()})
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
        if self.headers.get('Origin') not in (None, 'http://localhost:%d' % PORT, 'http://127.0.0.1:%d' % PORT):
            return self._json({'erro': 'origem recusada'}, 403)
        try:
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(min(n, 400000)) or b'{}')
            if self.path == '/api/alternar':
                return self._json({'ok': True, 'texto': alternar(body['arquivo'], int(body['linha']), body['texto'])})
            elif self.path == '/api/capturar':
                capturar(body.get('texto', ''))
            elif self.path == '/api/treino/dia':
                return self._json(treino.salvar_dia(VAULT, body))
            elif self.path == '/api/treino/despensa':
                return self._json(treino.salvar_despensa(VAULT, body))
            elif self.path == '/api/concierge':
                try:
                    return self._json(concierge.perguntar(body.get('pergunta'), _contexto(), capturar))
                except RuntimeError as e:
                    return self._json({'erro': str(e)}, 502)
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


if __name__ == '__main__':
    print('Orbitus em http://localhost:%d  (cofre: %s)' % (PORT, VAULT))
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
