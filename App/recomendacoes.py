# -*- coding: utf-8 -*-
"""Orbitus — mudanças de recomendação dos bancos (pedido de 12/11/2026: saber no mesmo dia).

Fonte: <Wealth>/05_RESEARCH/Indicações Externas.md, seção "Mudanças de recomendação", alimentada pela rotina
news-radar do Wealth (passo 3c). Somente leitura. Marca o que é ativo da carteira, para o push do mesmo dia.
"""
import json, os, re
from datetime import date, timedelta

import mesa


def _carteira(w):
    try:
        d = json.load(open(os.path.join(w, '00_System', '.automation_state', 'cockpit.json'), encoding='utf-8'))
    except (OSError, ValueError):
        return set()
    t = set()
    for k in ('acoes', 'fiis', 'etfs', 'outros'):
        for x in d.get(k) or []:
            if isinstance(x, dict) and x.get('ticker'):
                t.add(str(x['ticker']).upper().strip())
    return t


def _data(s):
    s = s.strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s) or None
    if m:
        return s[:10]
    m = re.match(r'(\d{2})/(\d{2})(?:/(\d{4}))?', s)
    if m:
        return '%s-%s-%s' % (m.group(3) or date.today().year, m.group(2), m.group(1))
    return ''


def ler(vault, dias=45):
    w = mesa.pasta_wealth(vault)
    try:
        txt = open(os.path.join(w, '05_RESEARCH', 'Indicações Externas.md'), encoding='utf-8').read()
    except OSError:
        return []
    sec = txt.split('## Mudanças de recomendação', 1)
    if len(sec) < 2:
        return []
    sec = sec[1].split('\n## ', 1)[0]
    cart = _carteira(w)
    corte = (date.today() - timedelta(days=dias)).isoformat()
    out = []
    for l in sec.splitlines():
        if not l.startswith('|') or l.startswith('|---') or l.startswith('| Data') or l.startswith('|Data'):
            continue
        c = [x.strip() for x in l.strip().strip('|').split('|')]
        if len(c) < 4:
            continue
        d = _data(c[0])
        if not d or d < corte:
            continue
        tk = re.sub(r'[^A-Z0-9]', '', c[2].upper())
        out.append({'data': d, 'banco': c[1], 'ticker': tk, 'mudanca': c[3], 'alvo': c[4] if len(c) > 4 else '',
                    'fech': c[5] if len(c) > 5 else '', 'var': c[6] if len(c) > 6 else '', 'd30': c[7] if len(c) > 7 else '',
                    'vs_cdi': c[8] if len(c) > 8 else '', 'fonte': c[9] if len(c) > 9 else '', 'carteira': tk in cart})
    out.sort(key=lambda r: r['data'], reverse=True)
    return out
