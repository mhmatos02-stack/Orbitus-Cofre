# -*- coding: utf-8 -*-
"""Orbitus — aba Treino (o antigo Shape Dezembro, agora com dados no cofre).

Pasta: <Orbitus>/20_Treino/
  dias/AAAA-MM-DD.json   um registro por dia (treino, séries, refeições, passos, peso, cintura, hábitos)
  despensa.json          estoque e favoritos de refeição
  resumo.json            números do dia calculados pela própria aba (para a Home e as órbitas)

Gravação atômica, sob trava. Se o arquivo no disco for mais novo que o enviado (campo "updated"),
o servidor recusa e devolve o atual, para não perder edição feita em outra janela.
"""
import json, os, re, threading
from datetime import date, datetime, timedelta

TRAVA = threading.Lock()
DATA = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _pasta(vault):
    p = os.path.join(vault, '20_Treino')
    os.makedirs(os.path.join(p, 'dias'), exist_ok=True)
    return p


def _ler(p, default=None):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _gravar(p, obj):
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1))
    os.replace(tmp, p)


def tudo(vault):
    p = _pasta(vault)
    dias = {}
    for n in sorted(os.listdir(os.path.join(p, 'dias'))):
        if n.endswith('.json') and DATA.match(n[:-5]):
            d = _ler(os.path.join(p, 'dias', n))
            if isinstance(d, dict):
                dias[n[:-5]] = d
    return {'dias': dias, 'despensa': _ler(os.path.join(p, 'despensa.json'), None),
            'locais': (_ler(os.path.join(p, 'locais.json'), {}) or {}).get('locais', []), 'mesa': mesa(vault)}


# ---------------------------------------------------------------- Mesa da Saúde
def _mesa_dir(vault):
    m = os.path.join(_pasta(vault), 'Mesa da Saúde')
    os.makedirs(os.path.join(m, 'pareceres'), exist_ok=True)
    return m


def mesa(vault):
    """Agentes (frontmatter dos .md em agentes/), últimos pareceres e perguntas."""
    m = _mesa_dir(vault)
    agentes = []
    ad = os.path.join(m, 'agentes')
    for n in sorted(os.listdir(ad)) if os.path.isdir(ad) else []:
        if not n.endswith('.md'):
            continue
        try:
            txt = open(os.path.join(ad, n), encoding='utf-8').read()
        except OSError:
            continue
        meta = {}
        if txt.startswith('---'):
            for l in txt.split('---')[1].strip().splitlines():
                if ':' in l:
                    k, v = l.split(':', 1)
                    meta[k.strip()] = v.strip().strip('"')
        meta['id'] = meta.get('id') or n[:-3]
        agentes.append(meta)
    agentes.sort(key=lambda a: int(a.get('ordem', 99)))
    pd = os.path.join(m, 'pareceres')
    pareceres = []
    for n in sorted(os.listdir(pd), reverse=True)[:14]:
        if n.endswith('.json'):
            d = _ler(os.path.join(pd, n))
            if isinstance(d, dict):
                pareceres.append(d)
    perguntas = []
    try:
        with open(os.path.join(m, 'perguntas.jsonl'), encoding='utf-8') as f:
            for l in f:
                l = l.strip()
                if l:
                    try:
                        perguntas.append(json.loads(l))
                    except ValueError:
                        pass
    except OSError:
        pass
    return {'agentes': agentes, 'pareceres': pareceres, 'perguntas': perguntas[-30:]}


def perguntar(vault, corpo):
    texto = re.sub(r'[\r\n]+', ' ', str(corpo.get('texto') or '')).strip()[:600]
    para = str(corpo.get('para') or 'mesa')[:40]
    if not texto:
        raise ValueError('escreva a pergunta')
    from datetime import datetime
    item = {'id': datetime.now().strftime('%Y%m%d%H%M%S'), 'data': datetime.now().isoformat(timespec='minutes'), 'para': para, 'texto': texto}
    with TRAVA:
        with open(os.path.join(_mesa_dir(vault), 'perguntas.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    return {'ok': True, 'pergunta': item}


def _salvar(p, obj):
    if not isinstance(obj, dict):
        raise ValueError('registro inválido')
    if len(json.dumps(obj)) > 200000:
        raise ValueError('registro grande demais')
    with TRAVA:
        atual = _ler(p)
        if isinstance(atual, dict) and (atual.get('updated') or 0) > (obj.get('updated') or 0):
            return {'ok': False, 'conflito': True, 'atual': atual}
        _gravar(p, obj)
    return {'ok': True}


def salvar_dia(vault, corpo):
    d = corpo.get('dia') or {}
    k = d.get('date', '')
    if not DATA.match(k):
        raise ValueError('data inválida')
    return _salvar(os.path.join(_pasta(vault), 'dias', k + '.json'), d)


def salvar_despensa(vault, corpo):
    return _salvar(os.path.join(_pasta(vault), 'despensa.json'), corpo.get('despensa'))


def salvar_resumo(vault, corpo):
    r = corpo.get('resumo')
    if not isinstance(r, dict) or len(json.dumps(r)) > 20000:
        raise ValueError('resumo inválido')
    with TRAVA:
        _gravar(os.path.join(_pasta(vault), 'resumo.json'), r)
    return {'ok': True}


# ---------------------------------------------------------------- resumo calculado no servidor
# (2026-10-30) Antes, só a página do treino gravava resumo.json: sem abrir a aba, a Home, o Concierge
# e a Mesa da Saúde liam números velhos. Agora o servidor recalcula os campos que vêm dos registros;
# os que dependem da gamificação (pontos, sequência, XP) continuam vindo da página quando ela grava no mesmo dia.
REFEICAO_PADRAO = {'cafe': (420, 35), 'almoco': (620, 45), 'lanche': (230, 28), 'jantar': (430, 40)}
NOMES = {'A': 'Peito + Costas', 'B1': 'Pernas', 'B2': 'Pernas · variação', 'C': 'Ombros + Braços', 'R': 'Corrida + ioga', 'V': 'Circuito de viagem'}
SINAIS = [('B2', {'afundo_rev', 'stiff_uni'}), ('B1', {'bulgaro', 'stiff', 'goblet', 'g_agach', 'g_legpress'}),
          ('A', {'sup_inc', 'rem_uni', 'sup_reto', 'g_supino', 'g_puxada'}), ('C', {'desenv', 'elev_lat', 'rosca', 'g_desenv', 'g_rosca_w'})]
_FOODS = {'t': 0, 'd': {}}


def _foods(vault):
    p = os.path.join(vault, 'App', 'static', 'treino.html')
    try:
        mt = os.path.getmtime(p)
    except OSError:
        return _FOODS['d']
    if mt != _FOODS['t']:
        txt = open(p, encoding='utf-8').read()
        _FOODS['d'] = {k: (u, float(kc), float(pr)) for k, u, kc, pr in
                       re.findall(r"(\w+):\{n:'[^']*',u:'(g|un)',(?:lb:'[^']*',)?def:[\d.]+,k:([\d.]+),p:([\d.]+)", txt)}
        _FOODS['t'] = mt
    return _FOODS['d']


def _nutricao(d, foods):
    k = p = 0.0
    for slot, v in (d.get('meals') or {}).items():
        if v is True:
            dk, dp = REFEICAO_PADRAO.get(slot, (0, 0)); k += dk; p += dp
        elif isinstance(v, dict):
            for it in v.get('items') or []:
                if it.get('f') in foods:
                    u, fk, fp = foods[it['f']]; m = (it.get('q') or 0) / 100.0 if u == 'g' else (it.get('q') or 0)
                    k += fk * m; p += fp * m
                else:
                    k += float(it.get('k') or 0); p += float(it.get('p') or 0)
    for x in d.get('extras') or []:
        k += float(x.get('k') or 0); p += float(x.get('p') or 0)
    return round(k), round(p)


def _treinou(d):
    w = d.get('workout') or {}
    return bool(w.get('done') or w.get('corrida') or w.get('yoga') or
                any(s and s.get('done') for v in (w.get('sets') or {}).values() for s in (v or [])))


def _sessao_de(d):
    w = d.get('workout') or {}
    if w.get('letter'):
        return w['letter'].replace('G', '') if w['letter'].startswith('G') else w['letter']
    ids = set((w.get('sets') or {}).keys())
    for letra, sin in SINAIS:
        if ids & sin:
            return letra
    return None


def _local(vault, k, d):
    if d.get('local'):
        return d['local']
    for L in (_ler(os.path.join(_pasta(vault), 'locais.json'), {}) or {}).get('locais', []):
        if L.get('de', '') <= k <= L.get('ate', ''):
            return L.get('local', 'casa')
    return 'casa'


def calcular(vault):
    t = tudo(vault)
    dias, foods, hoje = t['dias'], _foods(vault), date.today()
    k = hoje.isoformat()
    d = dias.get(k, {})
    ks = sorted(dias)
    peso = next((dias[x]['weight'] for x in reversed(ks) if dias[x].get('weight') is not None), None)
    cint = [(x, dias[x]['waist']) for x in ks if dias[x].get('waist') is not None]
    ult7 = [(hoje - timedelta(days=i)).isoformat() for i in range(7)]
    passos = [(dias[x].get('steps') or 0) + 100 * (dias[x].get('mov') or 0) for x in ult7 if x in dias and (dias[x].get('steps') is not None or dias[x].get('mov'))]
    kc, pr = _nutricao(d, foods)
    seg = hoje - timedelta(days=hoje.weekday())
    feitos = sum(1 for i in range(6) if (seg + timedelta(days=i)) <= hoje and _treinou(dias.get((seg + timedelta(days=i)).isoformat(), {})))
    # sessão de hoje: domingo = corrida + ioga; senão a próxima da sequência A, B1, C, A, B2, C
    if hoje.weekday() == 6:
        ses = 'R'
    else:
        ses = _sessao_de(d) if _treinou(d) else None
        if not ses:
            hist = [_sessao_de(dias[x]) for x in ks if x < k and _treinou(dias[x]) and _sessao_de(dias[x]) in ('A', 'B1', 'B2', 'C')]
            ult = hist[-1] if hist else 'C'
            ultimo_b = next((x for x in reversed(hist) if x in ('B1', 'B2')), 'B2')
            ses = {'A': 'B2' if ultimo_b == 'B1' else 'B1', 'B1': 'C', 'B2': 'C', 'C': 'A'}.get(ult, 'A')
    nome = NOMES.get(ses, ses) + (' · academia' if ses in ('A', 'B1', 'B2', 'C') and _local(vault, k, d) == 'academia' else '')
    return {'data': k, 'd12': (date(2026, 12, 12) - hoje).days, 'sessao': ses, 'sessao_nome': nome, 'treino_ok': _treinou(d),
            'peso': peso, 'peso_media7': None, 'peso_base': 71, 'cintura': cint[-1][1] if cint else None,
            'cintura_data': cint[-1][0] if cint else None, 'cintura_base': 92, 'cintura_meta': 87.5,
            'passos_hoje': d.get('steps'), 'mov_hoje': d.get('mov') or 0,
            'passos_media7': round(sum(passos) / len(passos)) if passos else None,
            'passos_meta': 8000 if k < '2026-11-10' else 10000, 'proteina': pr, 'proteina_meta': 140, 'kcal': kc, 'kcal_meta': 1850,
            'agua': d.get('water') or 0, 'agua_meta': 10, 'treinos_semana': feitos, 'treinos_alvo': 6}


def resumo(vault):
    """Para a Home, o Concierge e a Mesa: números recalculados dos registros + gamificação da página."""
    p = _pasta(vault)
    salvo = _ler(os.path.join(p, 'resumo.json'), {}) or {}
    try:
        r = calcular(vault)
    except Exception as e:
        print('treino: cálculo do resumo falhou:', e)
        r = {}
    for c in ('pontos', 'sequencia', 'xp', 'nivel', 'nivel_nome'):
        if c in salvo:
            r[c] = salvo[c]
    if salvo.get('data') == r.get('data'):
        for c in ('sessao', 'sessao_nome'):   # a página conhece trocas manuais de treino
            if salvo.get(c):
                r[c] = salvo[c]
    r['calculado_em'] = datetime.now().isoformat(timespec='minutes')
    try:
        with TRAVA:
            _gravar(os.path.join(p, 'resumo.json'), r)
    except OSError:
        pass
    hoje = date.today()
    seg = hoje - timedelta(days=hoje.weekday())
    semana = {}
    for i in range(7):
        k = (seg + timedelta(days=i)).isoformat()
        d = _ler(os.path.join(p, 'dias', k + '.json'))
        if not isinstance(d, dict):
            continue
        w = d.get('workout') or {}
        feito = bool(w.get('done')) or any(s and s.get('done') for v in (w.get('sets') or {}).values() for s in (v or []))
        if feito or w.get('yoga') or w.get('remo'):
            semana[k] = w.get('letter') or ('ioga/pilates' if w.get('yoga') else 'treino')
    r['semana'] = semana
    return r
