# -*- coding: utf-8 -*-
"""Orbitus — Agenda proativa: um dia de cada vez, com tudo que cai nele e o que fazer antes.

Junta: compromissos (ICS), tarefas com data, viagens (voos e estadias), proventos previstos e a agenda do
Wealth Office, feriados (Brasil, São Paulo, Alemanha-BW e Suíça-Berna nos dias da viagem) e datas do comércio.
Para cada dia: onde você estará, a previsão do tempo (Open-Meteo, grátis e sem chave, até 16 dias; depois disso
a média do roteiro da viagem) e o que levar. No alto, um radar com o que pede ação nas próximas semanas.
Somente leitura: não grava nada no cofre.
"""
import json, os, re, subprocess, threading, time, unicodedata, urllib.request
from datetime import date, datetime, timedelta

SP = ('São Paulo', -23.55, -46.63)
CACHE = {}
TRAVA = threading.Lock()

WMO = {0: ('☀️', 'céu limpo'), 1: ('🌤️', 'poucas nuvens'), 2: ('⛅', 'parcialmente nublado'), 3: ('☁️', 'nublado'),
       45: ('🌫️', 'neblina'), 48: ('🌫️', 'neblina'), 51: ('🌦️', 'garoa'), 53: ('🌦️', 'garoa'), 55: ('🌦️', 'garoa forte'),
       61: ('🌧️', 'chuva fraca'), 63: ('🌧️', 'chuva'), 65: ('🌧️', 'chuva forte'), 66: ('🌧️', 'chuva congelante'), 67: ('🌧️', 'chuva congelante'),
       71: ('🌨️', 'neve fraca'), 73: ('🌨️', 'neve'), 75: ('❄️', 'neve forte'), 77: ('🌨️', 'neve'), 80: ('🌦️', 'pancadas'),
       81: ('🌧️', 'pancadas fortes'), 82: ('⛈️', 'temporal'), 85: ('🌨️', 'neve'), 86: ('❄️', 'neve forte'),
       95: ('⛈️', 'trovoadas'), 96: ('⛈️', 'trovoadas com granizo'), 99: ('⛈️', 'trovoadas com granizo')}


def _sa(t):
    return re.sub(r'[̀-ͯ]', '', unicodedata.normalize('NFD', str(t or '').lower()))


# ------------------------------------------------------------------ datas fixas
def _pascoa(a):
    g, c = a % 19, a // 100
    h = (c - c // 4 - (8 * c + 13) // 25 + 19 * g + 15) % 30
    i = h - (h // 28) * (1 - (h // 28) * (29 // (h + 1)) * ((21 - g) // 11))
    j = (a + a // 4 + i + 2 - c + c // 4) % 7
    m = 3 + (i - j + 40) // 44
    return date(a, m, i - j + 28 - 31 * (m // 4))


def datas(ano):
    """[(data, nome, tipo, região)] tipo: feriado | data | comercio."""
    p = _pascoa(ano)
    out = [(date(ano, 1, 1), 'Ano-Novo', 'feriado', 'BR'), (p - timedelta(days=48), 'Carnaval', 'feriado', 'BR'),
           (p - timedelta(days=47), 'Carnaval', 'feriado', 'BR'), (p - timedelta(days=46), 'Quarta-feira de Cinzas (meio período)', 'data', 'BR'),
           (p - timedelta(days=2), 'Sexta-feira Santa', 'feriado', 'BR'), (p, 'Páscoa', 'data', 'BR'),
           (date(ano, 4, 21), 'Tiradentes', 'feriado', 'BR'), (date(ano, 5, 1), 'Dia do Trabalho', 'feriado', 'BR'),
           (p + timedelta(days=60), 'Corpus Christi', 'feriado', 'BR'), (date(ano, 9, 7), 'Independência', 'feriado', 'BR'),
           (date(ano, 10, 12), 'Nossa Senhora Aparecida · Dia das Crianças', 'feriado', 'BR'), (date(ano, 11, 2), 'Finados', 'feriado', 'BR'),
           (date(ano, 11, 15), 'Proclamação da República', 'feriado', 'BR'), (date(ano, 11, 20), 'Consciência Negra', 'feriado', 'BR'),
           (date(ano, 12, 24), 'Véspera de Natal', 'data', 'BR'), (date(ano, 12, 25), 'Natal', 'feriado', 'BR'),
           (date(ano, 12, 31), 'Véspera de Ano-Novo', 'data', 'BR'),
           (date(ano, 1, 25), 'Aniversário de São Paulo', 'feriado', 'SP'), (date(ano, 7, 9), 'Revolução Constitucionalista', 'feriado', 'SP'),
           # Alemanha (Baden-Württemberg) e Suíça (Berna): só aparecem nos dias em que você estiver lá
           (date(ano, 12, 25), 'Weihnachten (Natal)', 'feriado', 'DE'), (date(ano, 12, 26), 'Zweiter Weihnachtstag', 'feriado', 'DE'),
           (date(ano, 1, 1), 'Neujahr', 'feriado', 'DE'), (date(ano, 1, 6), 'Heilige Drei Könige (feriado em Baden-Württemberg)', 'feriado', 'DE'),
           (date(ano, 12, 25), 'Weihnachten', 'feriado', 'CH'), (date(ano, 12, 26), 'Stephanstag', 'feriado', 'CH'),
           (date(ano, 1, 1), 'Neujahr', 'feriado', 'CH'), (date(ano, 1, 2), 'Berchtoldstag (feriado em Berna)', 'feriado', 'CH')]
    # datas do comércio (ajudam a planejar presentes)
    nov = date(ano, 11, 1)
    qui = nov + timedelta(days=(3 - nov.weekday()) % 7 + 21)       # 4ª quinta de novembro
    out.append((qui + timedelta(days=1), 'Black Friday', 'comercio', 'BR'))
    mai = date(ano, 5, 1)
    out.append((mai + timedelta(days=(6 - mai.weekday()) % 7 + 7), 'Dia das Mães', 'comercio', 'BR'))
    ago = date(ano, 8, 1)
    out.append((ago + timedelta(days=(6 - ago.weekday()) % 7 + 7), 'Dia dos Pais', 'comercio', 'BR'))
    out.append((date(ano, 6, 12), 'Dia dos Namorados', 'comercio', 'BR'))
    return out


# ------------------------------------------------------------------ clima
def _baixar(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Orbitus'}), timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        r = subprocess.run(['/usr/bin/curl', '-sS', '--max-time', '15', url], capture_output=True, timeout=20)
        return json.loads(r.stdout.decode('utf-8') or '{}')


def clima(lat, lon):
    """Previsão diária (16 dias) para o ponto, em cache por 3 horas."""
    k = '%.2f,%.2f' % (lat, lon)
    with TRAVA:
        c = CACHE.get(k)
        if c and time.time() - c[0] < (10800 if c[1] else 300):   # falha fica só 5 min em cache
            return c[1]
    url = ('https://api.open-meteo.com/v1/forecast?latitude=%.3f&longitude=%.3f&daily=weather_code,temperature_2m_max,'
           'temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=16') % (lat, lon)
    try:
        j = _baixar(url).get('daily') or {}
        out = {}
        for i, d in enumerate(j.get('time') or []):
            cod = (j.get('weather_code') or [None])[i]
            ic, desc = WMO.get(cod, ('🌡️', ''))
            out[d] = {'icone': ic, 'texto': desc, 'max': round((j.get('temperature_2m_max') or [0])[i] or 0),
                      'min': round((j.get('temperature_2m_min') or [0])[i] or 0), 'chuva': (j.get('precipitation_probability_max') or [0])[i] or 0,
                      'fonte': 'previsão'}
    except Exception as e:
        print('agenda: clima falhou', e)
        out = {}
    with TRAVA:
        CACHE[k] = (time.time(), out)
    return out


# ------------------------------------------------------------------ onde você estará
def locais_por_dia(viagens):
    """{data: (nome, lat, lon, parada)} a partir dos roteiros (estadia cobre de..até; voo marca o dia de chegada)."""
    out = {}
    for v in viagens:
        ps = v.get('paradas') or []
        for p in ps:
            if p.get('lat') is None or not p.get('de'):
                continue
            try:
                d0 = date.fromisoformat(p['de'])
                d1 = date.fromisoformat(p.get('ate') or p['de'])
            except ValueError:
                continue
            d = d0
            while d <= d1:
                k = d.isoformat()
                # a estadia vale mais que o voo de chegada no mesmo dia
                if k not in out or p.get('tipo') == 'estadia':
                    out[k] = (p.get('nome') or v.get('titulo'), p['lat'], p['lon'], p, v.get('titulo'))
                d += timedelta(days=1)
    return out


def _regiao(lat, lon):
    if lat > 45 and 5.5 < lon < 10.6 and lat < 47.9:
        return 'CH'
    if lat > 47:
        return 'DE'
    return 'BR'


# ------------------------------------------------------------------ o que levar
REGRAS = [
    (r'anivers|niver|festa', ['Presente', 'Cartão']),
    (r'casamento', ['Presente', 'Roupa social']),
    (r'academia|treino|personal|hotel.*academia', ['Roupa de treino', 'Tênis', 'Garrafa de água']),
    (r'reuni|1:1|cliente|apresenta|workshop', ['Notebook e carregador']),
    (r'medic|dentista|exame|consulta|clinica|laborat', ['Documento com foto', 'Carteirinha do plano de saúde']),
    (r'\bvoo\b|aeroporto|embarque|gol\b|latam|azul\b', ['Documento com foto', 'Cartão de embarque', 'Carregador e fone']),
    (r'praia', ['Protetor solar', 'Roupa de banho', 'Chinelo']),
    (r'hotel|tivoli|hosped|check-?in', ['Mala', 'Carregador']),
    (r'banco|cartorio|cartório|detran|receita', ['Documento com foto']),
    (r'jantar|restaurante', []),
]


VERBO_CASA = re.compile(r'^(ligar|responder|mandar|enviar|pagar|revisar|conferir|escolher|decidir|verificar|comprar|ler|rodar|check|baixar|fechar|liberar|vender|aplicar|marcar|agendar)\b')


def levar(titulo):
    t = _sa(titulo).strip()
    if VERBO_CASA.match(t):
        return []          # coisa que se faz de casa ou no celular: não pede nada na mochila
    out = []
    for rx, itens in REGRAS:
        if re.search(rx, t):
            out += [i for i in itens if i not in out]
    return out


def levar_clima(c):
    if not c:
        return []
    out = []
    chuva, mx, mn = c.get('chuva') or 0, c.get('max'), c.get('min')
    mx = mx if mx is not None else 0
    mn = mn if mn is not None else 99
    if chuva >= 50:
        out.append('Guarda-chuva')
    if mx >= 30:
        out.append('Protetor solar e água')
    if mn <= 5:
        out += ['Casaco pesado', 'Luvas e gorro']
    elif mn <= 13:
        out.append('Casaco')
    return out


# ------------------------------------------------------------------ montagem
def montar(eventos, tarefas, viagens, wealth, locais_treino=None, dias=30, hoje=None):
    """eventos: {data: [[hora, titulo, tipo]]} · tarefas: lista do servidor (abertas) · viagens: estados completos ·
    wealth: estado do Wealth Office (proventos_proximos, agenda) · locais_treino: {data: 'academia'…}."""
    hoje = hoje or date.today()
    fim = hoje + timedelta(days=dias - 1)
    loc = locais_por_dia(viagens)
    datas_fixas = {}
    for a in {hoje.year, fim.year}:
        for d, nome, tipo, reg in datas(a):
            datas_fixas.setdefault(d.isoformat(), []).append((nome, tipo, reg))
    climas = {}

    def clima_do(k):
        nome, lat, lon = (loc[k][0], loc[k][1], loc[k][2]) if k in loc else SP
        ck = '%.2f,%.2f' % (lat, lon)
        if ck not in climas:
            climas[ck] = clima(lat, lon)
        c = climas[ck].get(k)
        if not c and k in loc and (loc[k][3].get('clima')):
            m = loc[k][3]['clima']
            c = {'icone': '📊', 'texto': 'média do período', 'max': m.get('max'), 'min': m.get('min'), 'chuva': None,
                 'fonte': 'média', 'nota': m.get('nota', '')}
        return c

    D = []
    d = hoje
    while d <= fim:
        k = d.isoformat()
        nome, lat, lon = (loc[k][0], loc[k][1], loc[k][2]) if k in loc else SP
        reg = _regiao(lat, lon)
        itens = []
        for e in eventos.get(k, []) or []:
            itens.append({'hora': '' if e[0] == 'dia todo' else e[0][:5], 'titulo': e[1], 'tipo': 'evento',
                          'cor': e[2] if len(e) > 2 else '', 'levar': levar(e[1])})
        for t in tarefas:
            if t.get('due') == k and not t.get('feito'):
                itens.append({'hora': t.get('hora') or '', 'titulo': t['titulo'], 'tipo': 'tarefa', 'area': t.get('tag'),
                              'detalhe': t.get('fonte') or '', 'levar': levar(t['titulo'])})
        for v in viagens:
            for p in v.get('paradas') or []:
                if p.get('de') == k and p.get('tipo') == 'voo' and p.get('hora'):
                    itens.append({'hora': p['hora'], 'titulo': p.get('nome'), 'tipo': 'viagem', 'detalhe': p.get('regiao') or '',
                                  'levar': levar('voo')})
                elif p.get('tipo') == 'estadia' and p.get('de') == k:
                    itens.append({'hora': '', 'titulo': 'Chegada: ' + str(p.get('nome')), 'tipo': 'viagem', 'detalhe': v.get('titulo') or '',
                                  'levar': list(p.get('levar') or [])})
                elif p.get('tipo') == 'estadia' and p.get('ate') == k:
                    itens.append({'hora': '', 'titulo': 'Saída: ' + str(p.get('nome')), 'tipo': 'viagem', 'detalhe': v.get('titulo') or '', 'levar': []})
        for pv in (wealth or {}).get('proventos_proximos') or []:
            if (pv.get('pgto') or '')[:10] == k:
                itens.append({'hora': '', 'titulo': 'Provento: ' + str(pv.get('ativo')), 'tipo': 'dinheiro',
                              'detalhe': '%s · %s' % ((pv.get('tipo') or '').lower(), pv.get('status') or ''), 'valor': pv.get('total')})
        for ag in (wealth or {}).get('agenda') or []:
            if (ag.get('data') or '')[:10] == k and ag.get('tipo') in ('resultado', 'prazo', 'fiscal', 'evento', 'copom', 'provento'):
                if ag.get('tipo') == 'provento' and any(i['tipo'] == 'dinheiro' and str(ag.get('ativo')) in i['titulo'] for i in itens):
                    continue
                itens.append({'hora': '', 'titulo': ag.get('evento'), 'tipo': 'mercado', 'detalhe': (ag.get('ativo') or ag.get('tipo') or '')})
        for nomef, tipo, r in datas_fixas.get(k, []):
            if r in ('BR', 'SP') and reg == 'BR' or r == reg:
                itens.append({'hora': '', 'titulo': nomef, 'tipo': 'feriado' if tipo == 'feriado' else 'data', 'detalhe': {'BR': 'Brasil', 'SP': 'São Paulo', 'DE': 'Alemanha', 'CH': 'Suíça'}[r]})
        tr = (locais_treino or {}).get(k)
        c = clima_do(k)
        lv = []
        for i in itens:
            lv += [x for x in i.get('levar') or [] if x not in lv]
        lv += [x for x in levar_clima(c) if x not in lv]
        if tr and 'academia' in str(tr) and 'Roupa de treino' not in lv:
            lv.append('Roupa de treino')
        itens.sort(key=lambda i: (i['hora'] == '', i['hora'] or '99', ['feriado', 'data', 'viagem', 'evento', 'tarefa', 'dinheiro', 'mercado'].index(i['tipo'])))
        D.append({'data': k, 'semana': ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'][d.weekday()], 'local': nome,
                  'viagem': loc[k][4] if k in loc else '', 'clima': c, 'itens': itens, 'levar': lv[:8],
                  'feriado': next((x['titulo'] for x in itens if x['tipo'] == 'feriado'), '')})
        d += timedelta(days=1)
    esp = datas_especiais(viagens, hoje)
    rd = radar(D, tarefas, hoje)
    for e in esp:
        dd = (date.fromisoformat(e['data']) - hoje).days
        if 0 <= dd <= 75:
            rd.append({'nivel': 'info', 'data': e['data'], 'texto': '%s (%s/%s, em %d dias): você estará em %s.' % (e['nome'], e['data'][8:], e['data'][5:7], dd, e['onde']), 'acao': ''})
    return {'dias': D, 'radar': rd, 'especiais': esp, 'gerado': datetime.now().isoformat(timespec='minutes')}


def radar(D, tarefas, hoje):
    """O que pede ação: feriado que fecha banco e B3, presente que falta, chuva em dia de compromisso, dia cheio, conflito, dinheiro entrando."""
    out = []

    def add(nivel, data, texto, acao=''):
        out.append({'nivel': nivel, 'data': data, 'texto': texto, 'acao': acao})
    abertas = [_sa(t['titulo']) for t in tarefas if not t.get('feito')]
    proventos = []
    for i, dia in enumerate(D):
        k, c = dia['data'], dia['clima'] or {}
        dd = (date.fromisoformat(k) - hoje).days
        quando = 'hoje' if dd == 0 else 'amanhã' if dd == 1 else '%s %s' % (dia['semana'], k[8:] + '/' + k[5:7])
        if dia['feriado'] and dd <= 14 and date.fromisoformat(k).weekday() < 5 and not dia['viagem']:
            add('info', k, '%s é %s: bancos e B3 fechados.' % (quando.capitalize(), dia['feriado']), 'Antecipe pagamentos e ordens.')
        compromissos = [x for x in dia['itens'] if x['tipo'] in ('evento', 'tarefa', 'viagem') and x['hora']]
        saidas = [x for x in compromissos if x['tipo'] == 'viagem' or levar(x['titulo'])]
        if (c.get('chuva') or 0) >= 60 and saidas and dd <= 7:
            add('atencao', k, '%s: %s%% de chance de chuva e você sai para %s às %s.' % (quando.capitalize(), c['chuva'], saidas[0]['titulo'], saidas[0]['hora']), 'Leve guarda-chuva e saia mais cedo.')
        if len(compromissos) >= 5 and dd <= 7:
            add('atencao', k, '%s está cheio: %d compromissos com hora.' % (quando.capitalize(), len(compromissos)), 'Veja se dá para mover algo.')
        hs = sorted(compromissos, key=lambda x: x['hora'])
        for a, b in zip(hs, hs[1:]):
            if _sa(a['titulo']) == _sa(b['titulo']):
                continue
            ma, mb = int(a['hora'][:2]) * 60 + int(a['hora'][3:5]), int(b['hora'][:2]) * 60 + int(b['hora'][3:5])
            if mb - ma < 45 and dd <= 14:
                add('atencao', k, '%s: %s (%s) e %s (%s) muito perto.' % (quando.capitalize(), a['titulo'], a['hora'], b['titulo'], b['hora']), 'Confirme o horário ou o deslocamento.')
        for x in dia['itens']:
            t = _sa(x['titulo'])
            if re.search(r'anivers|niver|casamento|cha de beb|batizado|formatura', t) and dd <= 21:
                quem = re.sub(r'^(festa de )?(aniversario|niver|casamento|batizado|formatura)( d[aoe]s?)?\s*', '', t).strip()
                tem = any('presente' in a and (not quem or quem.split(' ')[0] in a) for a in abertas)
                if not tem:
                    add('acao', k, '%s: %s. Ainda não há tarefa de presente.' % (quando.capitalize(), x['titulo']), 'Criar "Comprar presente" uns dias antes.')
            if x['tipo'] == 'dinheiro' and dd <= 10:
                proventos.append((k, x))
            if x['tipo'] == 'data' and 'Black Friday' in x['titulo'] and dd <= 30:
                add('info', k, 'Black Friday %s: boa data para os presentes da viagem (prazo 10/12).' % quando, '')
            if x['tipo'] == 'mercado' and dd <= 3:
                add('info', k, '%s: %s.' % (quando.capitalize(), x['titulo']), '')
        if dia['viagem'] and (i == 0 or D[i - 1]['viagem'] != dia['viagem']) and dd <= 30:
            add('info', k, '%s começa %s em %s.' % (dia['viagem'], quando, dia['local']), 'Veja a aba Viagem.')
    if proventos:
        tot = sum(float(x.get('valor') or 0) for _, x in proventos)
        add('dinheiro', proventos[0][0], 'Proventos previstos nos próximos 10 dias: %s%s.' % (
            ', '.join('%s (%s/%s)' % (x['titulo'].replace('Provento: ', ''), k[8:], k[5:7]) for k, x in proventos[:6]),
            (' · cerca de R$ %s' % ('{:,.2f}'.format(tot).replace(',', 'X').replace('.', ',').replace('X', '.'))) if tot else ''), 'A Mesa decide onde aplicar.')
    ordem = {'acao': 0, 'atencao': 1, 'dinheiro': 2, 'info': 3}
    out.sort(key=lambda r: (ordem.get(r['nivel'], 9), r['data']))
    return out[:12]


def datas_especiais(viagens, hoje=None):
    """Natal e Ano-Novo: onde você estará (para o radar e o Concierge)."""
    hoje = hoje or date.today()
    loc = locais_por_dia(viagens)
    out = []
    for mmdd, nome in (('12-25', 'Natal'), ('01-01', 'Ano-Novo')):
        a = hoje.year if mmdd >= hoje.strftime('%m-%d') else hoje.year + 1
        k = '%d-%s' % (a, mmdd)
        if nome == 'Ano-Novo' and k < hoje.isoformat():
            k = '%d-%s' % (hoje.year + 1, mmdd)
        out.append({'data': k, 'nome': nome, 'onde': loc[k][0] if k in loc else 'São Paulo (sem viagem marcada)'})
    return out
