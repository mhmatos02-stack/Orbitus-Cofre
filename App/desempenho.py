# -*- coding: utf-8 -*-
"""Orbitus — crescimento dos investimentos comparado ao CDI e à poupança (pedido de 11/11/2026).

Rentabilidade da carteira: a do próprio Wealth, sem cálculo paralelo. Vem do Performance Dashboard
(série semanal do 1:1 do CIO, Modified Dietz, que tira aportes e saques), contada a partir do "novo ponto zero" da série.
Se o Wealth publicar `performance` no cockpit.json, essa fonte tem prioridade.
CDI: Banco Central SGS 12 (diário). Poupança: SGS 195 (rentabilidade mensal por data de aniversário), pro rata dia.
Patrimônio: cockpit.json › historico (inclui aportes e saques: não é rentabilidade).
"""
import json, os, re
from datetime import date, datetime, timedelta

import mesa
import rendimentos

SGS = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.%d/dados?formato=json&dataInicial=%s&dataFinal=%s'


def _br(d):
    return d.strftime('%d/%m/%Y')


def _iso(s):
    return datetime.strptime(s, '%d/%m/%Y').date()


def _pct(s):
    m = re.search(r'([−\-+]?\d+(?:,\d+)?)\s*%', s or '')
    return float(m.group(1).replace('−', '-').replace(',', '.')) if m else None


def serie_carteira(w):
    """[(data, retorno acumulado %)] desde o novo ponto zero, lida da série semanal do Performance Dashboard."""
    p = os.path.join(w, '09_DASHBOARDS', 'Performance Dashboard.md')
    try:
        txt = open(p, encoding='utf-8').read()
    except OSError:
        return None, []
    zero, pts = None, []
    for l in txt.splitlines():
        if not l.startswith('| 20'):
            continue
        c = [x.strip() for x in l.strip().strip('|').split('|')]
        if len(c) < 6:
            continue
        d, jan = c[0][:10], c[1]
        if 'novo ponto zero da série' in jan:
            zero = d
            pts = [(d, 0.0)]
            continue
        if zero and ('desde o novo ponto zero' in jan) and d > zero:
            v = _pct(c[4])
            if v is not None:
                pts = [x for x in pts if x[0] != d] + [(d, v)]
    return zero, pts


def _baixar_sgs(vault, cod, ini, fim):
    cache = rendimentos._cache(vault, 'sgs_%d.json' % cod)
    c = rendimentos._ler_json(cache, {}) or {}
    if c.get('ini') == ini.isoformat() and c.get('baixado') == date.today().isoformat():
        return c.get('dados') or []
    try:
        dados = json.loads(rendimentos._get(SGS % (cod, _br(ini), _br(fim)), 30).decode('utf-8'))
        if isinstance(dados, list):
            rendimentos._gravar_json(cache, {'ini': ini.isoformat(), 'baixado': date.today().isoformat(), 'dados': dados})
            return dados
    except Exception as e:
        print('desempenho: SGS %d falhou: %s' % (cod, e))
    return c.get('dados') or []


def _cdi_acum(dados, ini, fim):
    """CDI acumulado de ini (exclusive) a fim (inclusive), %."""
    f = 1.0
    for x in dados:
        d = _iso(x['data'])
        if ini < d <= fim:
            f *= 1 + float(x['valor']) / 100
    return (f - 1) * 100


def _poup_acum(dados, ini, fim):
    """Poupança aplicada em ini: meses cheios pela taxa do aniversário; o mês corrente pro rata por dia."""
    taxas = {_iso(x['data']): float(x['valor']) for x in dados}
    if not taxas:
        return None

    def taxa(d):
        ks = [k for k in taxas if k <= d]
        return taxas[max(ks)] if ks else taxas[min(taxas)]
    f, a = 1.0, ini
    while True:
        prox = (a.replace(day=1) + timedelta(days=32)).replace(day=min(a.day, 28))
        r = taxa(a) / 100
        if prox <= fim:
            f *= 1 + r
            a = prox
        else:
            f *= (1 + r) ** ((fim - a).days / (prox - a).days)
            break
    return (f - 1) * 100


def _mensal(acum, dias):
    if acum is None or dias <= 0:
        return None
    return ((1 + acum / 100) ** (30.4375 / dias) - 1) * 100


def calcular(vault, cockpit=None):
    w = mesa.pasta_wealth(vault)
    perf = (cockpit or {}).get('performance')
    if isinstance(perf, dict) and perf.get('pontos'):
        zero, pts = perf.get('inicio'), [(p['data'], p['carteira']) for p in perf['pontos']]
        fonte = 'Wealth (cockpit.json › performance)'
    else:
        zero, pts = serie_carteira(w)
        fonte = 'Wealth · Performance Dashboard (série semanal do 1:1 do CIO, Modified Dietz)'
    hist = [{'data': h.get('data'), 'patrimonio': h.get('patrimonio')} for h in (cockpit or {}).get('historico') or []]
    out = {'ok': bool(pts and len(pts) > 1), 'inicio': zero, 'fonte': fonte, 'patrimonio': hist}
    if not out['ok']:
        out['erro'] = 'a série de rentabilidade do Wealth ainda não tem pontos depois do ponto zero'
        return out
    d0 = date.fromisoformat(zero)
    fim = date.fromisoformat(pts[-1][0])
    cdi = _baixar_sgs(vault, 12, d0, date.today())
    pou = _baixar_sgs(vault, 195, d0 - timedelta(days=40), date.today())
    serie = []
    for d, v in pts:
        dd = date.fromisoformat(d)
        serie.append({'data': d, 'carteira': round(v, 2), 'cdi': round(_cdi_acum(cdi, d0, dd), 2) if cdi else None,
                      'poupanca': round(_poup_acum(pou, d0, dd), 2) if pou and dd > d0 else (0.0 if pou else None)})
    dias = (fim - d0).days
    u = serie[-1]
    out.update(serie=serie, dias=dias,
               acumulado={'carteira': u['carteira'], 'cdi': u['cdi'], 'poupanca': u['poupanca']},
               media_mes={'carteira': _mensal(u['carteira'], dias), 'cdi': _mensal(u['cdi'], dias), 'poupanca': _mensal(u['poupanca'], dias)},
               fontes_bench='Banco Central: CDI diário (SGS 12) e poupança (SGS 195)')
    for k in out['media_mes']:
        if out['media_mes'][k] is not None:
            out['media_mes'][k] = round(out['media_mes'][k], 2)
    out['media_confiavel'] = dias >= 60      # menos que isso, uma semana ruim vira "média" e engana
    return out
