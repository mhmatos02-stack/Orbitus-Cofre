# -*- coding: utf-8 -*-
"""Orbitus — aba Wealth: o cockpit do AI Wealth Office dentro do Orbitus.

Fonte: <Wealth>/00_System/.automation_state/cockpit.json, gerado pelo próprio Wealth Office
(Scripts/cockpit_snapshot.py, a partir do Executive Dashboard que o launchd refaz 3x por dia).
Se o painel do Wealth for mais novo que a foto, o Orbitus pede uma foto nova (--sem-painel: não
busca cotação, só reempacota o que o Wealth já calculou). Somente leitura; nada é calculado aqui.
"""
import json, os, subprocess, sys, threading, time

import mesa

_TRAVA = threading.Lock()
_ULT = {'t': 0}


def _caminhos(vault):
    w = mesa.pasta_wealth(vault)
    return (w, os.path.join(w, '00_System', '.automation_state', 'cockpit.json'),
            os.path.join(w, '09_DASHBOARDS', 'Executive Dashboard.html'))


def _refazer(w):
    try:
        subprocess.run([sys.executable, os.path.join(w, 'Scripts', 'cockpit_snapshot.py'), '--sem-painel'],
                       cwd=w, capture_output=True, timeout=90)
    except Exception as e:
        print('wealth: snapshot falhou:', e, file=sys.stderr)


def estado(vault):
    w, js, html = _caminhos(vault)
    velho = (not os.path.exists(js)) or (os.path.exists(html) and os.path.getmtime(html) > os.path.getmtime(js) + 5)
    if velho and time.time() - _ULT['t'] > 120 and _TRAVA.acquire(blocking=False):
        _ULT['t'] = time.time()
        try:
            if not os.path.exists(js):
                _refazer(w)                     # primeira vez: espera
            else:
                threading.Thread(target=_refazer, args=(w,), daemon=True).start()   # depois: em segundo plano
        finally:
            _TRAVA.release()
    try:
        with open(js, encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        return {'disponivel': False, 'erro': str(e)}
    d['disponivel'] = True
    d['atualizando'] = velho
    return d
