# -*- coding: utf-8 -*-
"""Orbitus — aba Wealth: o cockpit do AI Wealth Office dentro do Orbitus.

Fonte: <Wealth>/00_System/.automation_state/cockpit.json, gerado pelo próprio Wealth Office
(Scripts/cockpit_snapshot.py, a partir do Executive Dashboard que o launchd refaz 3x por dia).
Se o painel do Wealth for mais novo que a foto, o Orbitus pede uma foto nova (--sem-painel: não
busca cotação, só reempacota o que o Wealth já calculou). Somente leitura; nada é calculado aqui.
"""
import json, os, subprocess, sys, threading, time

import mesa
import rendimentos
import desempenho
import wealth_rotinas

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
    # saúde das automações do Wealth (o que é o amarelo/vermelho), lida do Health Check do próprio Wealth
    try:
        d['saude_wealth'] = wealth_rotinas.status_automacao(w)
    except Exception:
        d['saude_wealth'] = None
    _radar_precos(w, d)
    try:
        d['rendimentos'] = rendimentos.calcular(vault, d)
    except Exception as e:
        d['rendimentos'] = {'ok': False, 'erro': str(e)[:160]}
    try:
        d['desempenho'] = desempenho.calcular(vault, d)
    except Exception as e:
        d['desempenho'] = {'ok': False, 'erro': str(e)[:160]}
    return d


def _radar_precos(w, d):
    """Preço da última triagem (03_PORTFOLIO/radar_oportunidades.csv) e a referência da régua do Radar:
    preço em que o DY dos últimos 12 meses chega a 9,5% (DY + crescimento real ≥ ~9,5%, sem contar crescimento).
    Não é valor justo: o teto de entrada oficial só sai do Fluxo 1."""
    import csv
    rd = d.get('radar') or {}
    if not rd.get('top'):
        return
    precos = {}
    try:
        with open(os.path.join(w, '03_PORTFOLIO', 'radar_oportunidades.csv'), encoding='utf-8') as f:
            for row in csv.DictReader(f):
                t = (row.get('ticker') or '').strip()
                if t and (t not in precos or row.get('data', '') >= precos[t][1]):
                    precos[t] = (row.get('preco'), row.get('data', ''), row.get('dy'))
    except OSError:
        return
    for r in rd['top']:
        p, dt, dyc = precos.get(r.get('ticker'), (None, '', None))
        try:
            p = float(p)
        except (TypeError, ValueError):
            continue
        r['preco'], r['preco_data'] = p, dt
        try:
            dy = float(dyc if dyc not in (None, '') else r.get('dy'))   # DY da mesma linha do preço
            r['dy'] = dy
            if dy > 0:
                r['teto_regua'] = round(p * dy / 9.5, 2)
        except (TypeError, ValueError):
            pass
