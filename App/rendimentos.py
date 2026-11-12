# -*- coding: utf-8 -*-
"""Orbitus — quanto rende cada título do Tesouro e cada cofrinho, por dia e por mês (pedido de 11/11/2026).

Somente leitura dos dados do AI Wealth Office:
  - quantidades: <Wealth>/03_PORTFOLIO/tesouro_quantidades.csv
  - saldos dos cofrinhos: <Wealth>/03_PORTFOLIO/valores_ref.csv
  - taxas contratadas: cockpit.json (tesouro_marcacao), IPCA esperado: parametros.csv
Fontes públicas, com cache no Orbitus (00_Sistema/cache/):
  - preço diário de cada título: Tesouro Transparente (CSV oficial, PU de venda da manhã);
  - CDI do dia: Banco Central, série SGS 12.

Tesouro "realizado" = quantidade x variação do preço de venda (marcação a mercado: pode ser negativo num dia).
Tesouro "na curva" = o que o título rende por mês se for mantido até o vencimento, pela taxa contratada.
Cofrinho = saldo x CDI x % do CDI (estimativa; o banco não manda o rendimento diário).
Tudo bruto, antes do IR.
"""
import csv, io, json, os, subprocess, threading, time, urllib.request
from datetime import date, datetime, timedelta

import mesa

CSV_URL = ('https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/'
           'resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv')
CDI_URL = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados/ultimos/1?formato=json'
DU_MES = 21
_TRAVA = threading.Lock()
_TENTOU = {'pu': 0.0, 'cdi': 0.0}


def _cache(vault, nome):
    p = os.path.join(vault, '00_Sistema', 'cache')
    os.makedirs(p, exist_ok=True)
    return os.path.join(p, nome)


def _ler_json(p, padrao=None):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _gravar_json(p, obj):
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, p)


def _iso(br):
    d, m, a = br.strip().split('/')
    return '%s-%s-%s' % (a, m, d)


def _f(x):
    return float(str(x).replace('.', '').replace(',', '.')) if ',' in str(x) else float(x)


def _get(url, timeout=90):
    """urllib; se o Python do Mac reclamar do certificado (problema conhecido no macOS), usa o curl do sistema."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Orbitus/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        out = subprocess.run(['/usr/bin/curl', '-sSL', '--max-time', str(timeout), url], capture_output=True, timeout=timeout + 10)
        if out.returncode != 0 or not out.stdout:
            raise ConnectionError('curl %s: %s (antes: %s)' % (out.returncode, out.stderr.decode()[:120], e))
        return out.stdout


def _titulos(w):
    out = []
    try:
        with open(os.path.join(w, '03_PORTFOLIO', 'tesouro_quantidades.csv'), encoding='utf-8') as f:
            for r in csv.DictReader(f):
                try:
                    q = float(r['quantidade'])
                except (KeyError, ValueError):
                    continue
                if q > 0:
                    out.append({'ticker': r['ticker'], 'tipo': r['tipo_csv_oficial'], 'vencimento': r['vencimento'], 'quantidade': q,
                                'custodia': r.get('custodia', ''), 'confirmado_em': r.get('data_confirmacao', '')})
    except OSError:
        pass
    return out


def _baixar_pu(vault, titulos):
    """Baixa o CSV oficial (~15 MB) e guarda só a série dos títulos da carteira nos últimos ~14 meses."""
    try:
        raw = _get(CSV_URL, 120).decode('utf-8-sig', errors='replace')
        alvo = {(t['tipo'], t['vencimento']) for t in titulos}
        corte = (date.today() - timedelta(days=430)).isoformat()
        series = {}
        for r in csv.DictReader(io.StringIO(raw), delimiter=';'):
            try:
                k = (r['Tipo Titulo'].strip(), _iso(r['Data Vencimento']))
                if k not in alvo:
                    continue
                db = _iso(r['Data Base'])
                if db < corte:
                    continue
                series.setdefault('%s|%s' % k, {})[db] = _f(r['PU Venda Manha'])
            except (KeyError, ValueError):
                continue
        if series:
            _gravar_json(_cache(vault, 'tesouro_pu.json'), {'baixado_em': datetime.now().isoformat(timespec='minutes'),
                                                            'fonte': 'Tesouro Transparente (CSV oficial, PU de venda da manhã)',
                                                            'series': series})
    except Exception as e:
        print('rendimentos: Tesouro Transparente falhou:', e)


def _baixar_cdi(vault):
    try:
        j = json.loads(_get(CDI_URL, 20).decode('utf-8'))[-1]
        _gravar_json(_cache(vault, 'cdi.json'), {'data': _iso(j['data']), 'taxa_dia': float(j['valor']),
                                                 'baixado_em': datetime.now().isoformat(timespec='minutes'),
                                                 'fonte': 'Banco Central, SGS 12 (CDI diário)'})
    except Exception as e:
        print('rendimentos: CDI do BCB falhou:', e)


def _ultimo_dia_util(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _atualizar(vault, titulos):
    """Em segundo plano: baixa o que estiver velho. Tenta de novo no máximo a cada 30 min."""
    pu = _ler_json(_cache(vault, 'tesouro_pu.json'), {}) or {}
    cdi = _ler_json(_cache(vault, 'cdi.json'), {}) or {}
    esperado = _ultimo_dia_util(date.today()).isoformat()
    datas = [max(s) for s in (pu.get('series') or {}).values() if s]
    precisa_pu = (not datas or max(datas) < esperado or
                  len(pu.get('series') or {}) < len({(t['tipo'], t['vencimento']) for t in titulos}))
    if precisa_pu and (pu.get('baixado_em') or '')[:13] == datetime.now().isoformat()[:13]:
        precisa_pu = False      # já baixou nesta hora e o Tesouro ainda não publicou o dia
    precisa_cdi = (cdi.get('data') or '') < esperado and (cdi.get('baixado_em') or '')[:13] != datetime.now().isoformat()[:13]
    agora = time.time()
    tarefas = []
    if precisa_pu and agora - _TENTOU['pu'] > 1800:
        _TENTOU['pu'] = agora
        tarefas.append(lambda: _baixar_pu(vault, titulos))
    if precisa_cdi and agora - _TENTOU['cdi'] > 1800:
        _TENTOU['cdi'] = agora
        tarefas.append(lambda: _baixar_cdi(vault))
    if tarefas:
        def rodar():
            if _TRAVA.acquire(blocking=False):
                try:
                    for t in tarefas:
                        t()
                finally:
                    _TRAVA.release()
        threading.Thread(target=rodar, daemon=True).start()
    return bool(tarefas)


def _parametro(w, chave):
    try:
        with open(os.path.join(w, '03_PORTFOLIO', 'parametros.csv'), encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('chave') == chave:
                    return float(r['valor'])
    except (OSError, ValueError, KeyError):
        pass
    return None


def _cofrinhos(w):
    out = []
    try:
        with open(os.path.join(w, '03_PORTFOLIO', 'valores_ref.csv'), encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if 'cofrinho' in (r.get('ticker') or '').lower():
                    out.append({'nome': r['ticker'], 'saldo': float(r['valor_atual']), 'data': r.get('data', '')})
    except (OSError, ValueError, KeyError):
        pass
    return out


def calcular(vault, cockpit=None):
    w = mesa.pasta_wealth(vault)
    titulos = _titulos(w)
    atualizando = _atualizar(vault, titulos)
    pu = _ler_json(_cache(vault, 'tesouro_pu.json'), {}) or {}
    cdi = _ler_json(_cache(vault, 'cdi.json'), {}) or {}
    cfg = _ler_json(os.path.join(vault, '00_Sistema', 'rendimentos.json'), {}) or {}
    hoje = date.today()
    ini_mes = hoje.replace(day=1).isoformat()
    ipca = _parametro(w, 'ipca_focus_ano_seguinte') or _parametro(w, 'ipca_focus_ano_corrente')
    cdi_dia = cdi.get('taxa_dia')                               # % ao dia
    cdi_ano = ((1 + cdi_dia / 100) ** 252 - 1) * 100 if cdi_dia else None
    taxas = {t.get('ticker'): t.get('taxa_contratada_media') for t in ((cockpit or {}).get('tesouro_marcacao') or {}).get('titulos') or []}

    lin = []
    for t in titulos:
        s = (pu.get('series') or {}).get('%s|%s' % (t['tipo'], t['vencimento'])) or {}
        datas = sorted(s)
        r = dict(t, valor=None, ontem=None, ontem_data='', mes=None, media_dia=None, curva_mes=None, taxa=taxas.get(t['ticker']))
        if datas:
            q, ult = t['quantidade'], datas[-1]
            r['valor'] = round(q * s[ult], 2)
            r['pu_data'] = ult
            if len(datas) >= 2:
                r['ontem'] = round(q * (s[ult] - s[datas[-2]]), 2)
                r['ontem_data'] = ult
            base = [x for x in datas if x < ini_mes]
            if base:
                r['mes'] = round(q * (s[ult] - s[base[-1]]), 2)
                du = len([x for x in datas if x >= ini_mes])
                r['media_dia'] = round(r['mes'] / du, 2) if du else None
            if datas[0] > (hoje - timedelta(days=400)).isoformat():
                r['aviso'] = 'série curta'
        # na curva: rendimento esperado por mês se mantiver (taxa contratada; IPCA esperado do Focus; Selic pelo CDI)
        tx, tipo = r.get('taxa'), t['tipo'].lower()
        anual = None
        if 'selic' in tipo:
            anual = cdi_ano
        elif 'prefixado' in tipo and tx is not None:
            anual = tx
        elif tx is not None and ipca is not None:
            anual = ((1 + ipca / 100) * (1 + tx / 100) - 1) * 100
        if anual is not None and r['valor']:
            r['curva_mes'] = round(r['valor'] * ((1 + anual / 100) ** (1 / 12) - 1), 2)
            r['curva_ano'] = round(r['valor'] * anual / 100, 2)
            r['curva_ano_pct'] = round(anual, 2)
        if 'juros semestrais' in tipo:
            r['nota'] = 'paga cupom em jan e jul: no dia do cupom o preço cai e o valor vai para a conta'
        lin.append(r)

    cof = []
    for c in _cofrinhos(w):
        pct = float((cfg.get('pct_cdi') or {}).get(c['nome'], 100))
        d = dict(c, pct_cdi=pct, pct_confirmado=c['nome'] in (cfg.get('pct_cdi') or {}))
        if cdi_dia:
            td = cdi_dia / 100 * pct / 100
            d['dia'] = round(c['saldo'] * td, 2)
            d['mes'] = round(c['saldo'] * ((1 + td) ** DU_MES - 1), 2)
            d['ano'] = round(c['saldo'] * ((1 + td) ** 252 - 1), 2)
            d['_td'] = td
        cof.append(d)

    # crescimento projetado em 12 meses: Tesouro na curva de cada título, cofrinhos pelo CDI de hoje, sem aportes nem resgates
    proj = []
    for m in range(13):
        tz = sum(x['valor'] * (1 + x['curva_ano_pct'] / 100) ** (m / 12) for x in lin if x.get('valor') and x.get('curva_ano_pct') is not None)
        cf = sum(c['saldo'] * (1 + c['_td']) ** (DU_MES * m) for c in cof if c.get('_td'))
        mes = (hoje.month - 1 + m) % 12 + 1
        proj.append({'m': m, 'rotulo': '%02d/%02d' % (mes, (hoje.year + (hoje.month - 1 + m) // 12) % 100),
                     'tesouro': round(tz, 2), 'cofrinhos': round(cf, 2)})
    for c in cof:
        c.pop('_td', None)

    def soma(xs, k):
        v = [x[k] for x in xs if x.get(k) is not None]
        return round(sum(v), 2) if v else None
    return {'ok': bool(lin or cof), 'atualizando': atualizando, 'titulos': lin, 'cofrinhos': cof,
            'total': {'valor': soma(lin, 'valor'), 'ontem': soma(lin, 'ontem'), 'mes': soma(lin, 'mes'), 'curva_mes': soma(lin, 'curva_mes'),
                      'cofrinho_dia': soma(cof, 'dia'), 'cofrinho_mes': soma(cof, 'mes'), 'cofrinho_saldo': soma(cof, 'saldo'),
                      'curva_ano': soma(lin, 'curva_ano'), 'cofrinho_ano': soma(cof, 'ano')},
            'projecao': proj,
            'cdi': {'dia': cdi_dia, 'ano': round(cdi_ano, 2) if cdi_ano else None, 'data': cdi.get('data')},
            'ipca_esperado': ipca, 'pu_baixado_em': pu.get('baixado_em'), 'mes_ref': ini_mes[:7],
            'fontes': 'Tesouro Transparente (preço de venda diário) · Banco Central SGS 12 (CDI) · quantidades e saldos do Wealth'}
