# -*- coding: utf-8 -*-
"""Orbitus — o dia em ordem de horário: rotina que se repete + tarefas com data + compromissos da agenda.

Rotina:  <cofre>/10_Tarefas/Rotina diária.md   (você edita no Obsidian; uma linha por item)
           - 08:00 Tomar as vitaminas
           - 09:00 Fazer o treino do dia [seg-sáb]
           - 10:00 Ioga [sáb, dom]
         Sem [dias] = todos os dias. Sem horário = "qualquer hora".
Feitos:  <cofre>/10_Tarefas/Rotina/AAAA-MM.json   {"AAAA-MM-DD": {"<id>": "HH:MM"}}
Itens com treino, ioga, pilates, corrida ou água no texto são marcados sozinhos quando você registra na aba Treino.
"""
import json, os, re, threading, unicodedata
from datetime import date, datetime

TRAVA = threading.Lock()
ARQ = os.path.join('10_Tarefas', 'Rotina diária.md')
DIAS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom']
LINHA = re.compile(r'^\s*[-*]\s+(?!\[)(?:(\d{1,2})[:h](\d{2})\s+)?(.+?)(?:\s*\[([^\]]+)\])?\s*$')
HORA_TXT = re.compile(r'⏰\s*(\d{1,2})[:h](\d{2})')
AGUA_LINHA = re.compile(r'^\s*[-*]\s+[aá]gua\s*:', re.I)


def agua_cfg(vault):
    """Meta de água: a linha '- água: 10 copos de 250 ml, das 08:00 às 20:00' da rotina (senão 10 copos, 08–20h)."""
    cfg = {'meta': 10, 'ml': 250, 'ini': '08:00', 'fim': '20:00'}
    try:
        for l in open(os.path.join(vault, ARQ), encoding='utf-8').read().splitlines():
            if AGUA_LINHA.match(l):
                m = re.search(r'(\d+)\s*copos?', l)
                if m:
                    cfg['meta'] = max(1, min(20, int(m.group(1))))
                m = re.search(r'(\d{2,3})\s*ml', l)
                if m:
                    cfg['ml'] = int(m.group(1))
                hs = ['%02d:%s' % (int(a), b) for a, b in re.findall(r'(\d{1,2})[:h](\d{2})', l)]
                if len(hs) >= 2 and hs[0] < hs[1]:
                    cfg['ini'], cfg['fim'] = hs[0], hs[1]
                break
    except OSError:
        pass
    return cfg


def agua_slots(cfg):
    """Espalha a meta em lembretes a cada ~2 h: [(hora, copos, acumulado)]."""
    a = int(cfg['ini'][:2]) * 60 + int(cfg['ini'][3:])
    b = int(cfg['fim'][:2]) * 60 + int(cfg['fim'][3:])
    n = max(1, min((cfg['meta'] + 1) // 2, (b - a) // 90 + 1))
    base, resto = divmod(cfg['meta'], n)
    out, acum = [], 0
    for i in range(n):
        c = base + (1 if i < resto else 0)
        acum += c
        t = a + round(i * (b - a) / max(1, n - 1)) if n > 1 else a
        out.append(('%02d:%02d' % (t // 60, t % 60), c, acum))
    return out

MODELO = """# Rotina diária

Itens que se repetem e aparecem na lista do dia, embaixo do calendário do Orbitus.
Formato: `- HH:MM Texto [dias]`. Sem [dias] = todos os dias. Sem horário = qualquer hora.
Dias: seg, ter, qua, qui, sex, sáb, dom, ou um intervalo como seg-sex.
Marcar treino, ioga, pilates ou corrida aqui também marca na aba Treino (e pontua), e vice-versa.
A linha `- água: …` vira lembretes de água espalhados no dia; marcar um deles soma os copos no contador de água do Treino.
Coisa de um dia só (ex.: arrumar a mala) é tarefa normal com data e hora: `- [ ] Arrumar a mala 📅 2026-10-31 ⏰ 12:30`.

- água: 10 copos de 250 ml, das 08:00 às 20:00
- 08:00 Tomar as vitaminas
- 09:00 Fazer o treino do dia [seg-sáb]
- 09:00 Corrida leve de 30 a 40 min [dom]
- 10:00 Ioga [sáb, dom]
- 21:00 Aula de espanhol no Duolingo
"""


def _sa(t):
    return re.sub(r'[̀-ͯ]', '', unicodedata.normalize('NFD', str(t).lower()))


def _dias(spec):
    if not spec:
        return list(range(7))
    out = set()
    for parte in re.split(r'[,;/ ]+', _sa(spec)):
        parte = parte.strip()
        if not parte:
            continue
        if parte in ('todos', 'diario', 'todo'):
            return list(range(7))
        if parte in ('uteis', 'semana'):
            out |= set(range(5))
            continue
        if parte in ('fds', 'fim'):
            out |= {5, 6}
            continue
        m = re.match(r'^([a-z]{3})[a-z]*-([a-z]{3})[a-z]*$', parte)
        if m and m.group(1) in DIAS and m.group(2) in DIAS:
            a, b = DIAS.index(m.group(1)), DIAS.index(m.group(2))
            i = a
            while True:
                out.add(i)
                if i == b:
                    break
                i = (i + 1) % 7
            continue
        if parte[:3] in DIAS:
            out.add(DIAS.index(parte[:3]))
    return sorted(out) if out else list(range(7))


def _liga(texto):
    t = _sa(texto)
    if 'ioga' in t or 'yoga' in t:
        return 'ioga'
    if 'pilates' in t:
        return 'pilates'
    if 'corrida' in t or 'correr' in t:
        return 'corrida'
    if 'treino' in t:
        return 'treino'
    m = re.search(r'(\d+)\s*copos? de agua', t)
    if m:
        return 'agua:' + m.group(1)
    return None


def itens(vault):
    """Lê a rotina (cria o arquivo com o modelo na primeira vez)."""
    p = os.path.join(vault, ARQ)
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(MODELO)
    out = []
    try:
        linhas = open(p, encoding='utf-8').read().splitlines()
    except OSError:
        return out
    for l in linhas:
        if AGUA_LINHA.match(l):
            continue
        m = LINHA.match(l)
        if not m:
            continue
        hora = '%02d:%s' % (int(m.group(1)), m.group(2)) if m.group(1) else ''
        texto = m.group(3).strip()
        iid = re.sub(r'[^a-z0-9]+', '-', _sa(texto)).strip('-')[:48] or 'item'
        out.append({'id': iid, 'hora': hora, 'texto': texto, 'dias': _dias(m.group(4)), 'liga': _liga(texto)})
    return out


def _arq_feitos(vault, dia):
    return os.path.join(vault, '10_Tarefas', 'Rotina', dia[:7] + '.json')


def _ler(p):
    try:
        with open(p, encoding='utf-8') as f:
            j = json.load(f)
        return j if isinstance(j, dict) else {}
    except (OSError, ValueError):
        return {}


def feitos(vault, dia):
    return _ler(_arq_feitos(vault, dia)).get(dia, {})


def _id_evento(titulo):
    """Id estável de um evento da agenda (para marcar como feito): 'ev-' + título sem acento, em minúsculas."""
    t = unicodedata.normalize('NFD', str(titulo or '')).encode('ascii', 'ignore').decode().lower()
    return ('ev-' + re.sub(r'[^a-z0-9]+', '-', t).strip('-')[:45]).rstrip('-')


def marcar(vault, corpo):
    dia, iid, feito = str(corpo.get('dia') or ''), str(corpo.get('id') or ''), bool(corpo.get('feito'))
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', dia) or not re.match(r'^[a-z0-9-]{1,48}$', iid):
        raise ValueError('item inválido')
    if dia > date.today().isoformat():
        raise ValueError('não dá para marcar um dia que ainda não chegou')
    if iid.startswith('agua-'):
        slots = agua_slots(agua_cfg(vault))
        i = int(iid[5:]) - 1 if iid[5:].isdigit() else -1
        if not 0 <= i < len(slots):
            raise ValueError('lembrete de água inválido')
        c = slots[i][1]
        _treino(vault, dia, lambda d: d.__setitem__('water', max(0, min(20, int(d.get('water') or 0) + (c if feito else -c)))))
        return {'ok': True}
    it = next((x for x in itens(vault) if x['id'] == iid), None)
    lg = (it or {}).get('liga') or ''
    if lg in ('treino', 'ioga', 'pilates', 'corrida'):
        def aplica(d):
            w = d.setdefault('workout', {'letter': None, 'sets': {}, 'done': False, 'warm': False, 'remo': False})
            if lg == 'treino':
                w['done'] = feito
            elif lg == 'ioga':
                w['yoga'] = feito
                w['rec'] = 'ioga' if feito else None
            else:
                w[lg] = feito
        _treino(vault, dia, aplica)
    p = _arq_feitos(vault, dia)
    with TRAVA:
        j = _ler(p)
        d = j.setdefault(dia, {})
        if feito:
            d[iid] = datetime.now().strftime('%H:%M')
            d.pop('-' + iid, None)
        else:
            d.pop(iid, None)
            d['-' + iid] = 1      # desmarcado à mão: vale mais que a marcação automática do Treino
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(j, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    return {'ok': True}


def _treino(vault, dia, fn):
    """Altera o registro do dia da aba Treino (com 'updated' novo, para a aba adotar o valor e pontuar)."""
    try:
        import treino as _tr
        trava = _tr.TRAVA
    except Exception:
        trava = TRAVA
    p = os.path.join(vault, '20_Treino', 'dias', dia + '.json')
    with trava:
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {'date': dia, 'weight': None, 'waist': None, 'steps': None, 'sleep': None, 'water': 0, 'meals': {},
                 'extras': [], 'habits': {}, 'workout': {'letter': None, 'sets': {}, 'done': False, 'warm': False, 'remo': False}}
        fn(d)
        d['updated'] = int(datetime.now().timestamp() * 1000)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(json.dumps(d, ensure_ascii=False, indent=1))
        os.replace(tmp, p)


def _auto(vault, dia):
    """O que a aba Treino já registrou nesse dia."""
    try:
        with open(os.path.join(vault, '20_Treino', 'dias', dia + '.json'), encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    w = d.get('workout') or {}
    feito = bool(w.get('done')) or any(s and s.get('done') for v in (w.get('sets') or {}).values() for s in (v or []))
    return {'treino': feito, 'ioga': bool(w.get('yoga')), 'pilates': bool(w.get('pilates')),
            'corrida': bool(w.get('corrida')), 'agua': int(d.get('water') or 0)}


def agua_estado(vault, d_iso, bebidos=None):
    """Água do dia num lugar só (não polui a lista): bebidos, meta e o ritmo esperado até agora."""
    cfg = agua_cfg(vault)
    if bebidos is None:
        bebidos = _auto(vault, d_iso).get('agua', 0)
    sl = agua_slots(cfg)
    hoje = date.today().isoformat()
    if d_iso < hoje:
        esperado = cfg['meta']
    elif d_iso > hoje:
        esperado = 0
    else:
        hm = datetime.now().strftime('%H:%M')
        esperado = max([a for h, c, a in sl if h <= hm] or [0])
    prox = next((h for h, c, a in sl if a > bebidos and (d_iso != hoje or h > datetime.now().strftime('%H:%M'))), '')
    return {'bebidos': bebidos, 'meta': cfg['meta'], 'ml': cfg['ml'], 'esperado': esperado, 'atras': max(0, esperado - bebidos),
            'slots': sl, 'proximo': prox}


def agua_somar(vault, d_iso, delta):
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(d_iso)) or d_iso > date.today().isoformat():
        raise ValueError('dia inválido')
    delta = int(delta)
    if not -10 <= delta <= 10:
        raise ValueError('quantidade inválida')
    _treino(vault, d_iso, lambda d: d.__setitem__('water', max(0, min(20, int(d.get('water') or 0) + delta))))
    return dict(agua_estado(vault, d_iso), ok=True)


def hora_da_tarefa(corpo):
    m = HORA_TXT.search(corpo) or re.search(r'\b(?:às|as)\s+(\d{1,2})[:h](\d{2})\b', corpo)
    return '%02d:%s' % (int(m.group(1)), m.group(2)) if m else ''


def dia(vault, d_iso, tarefas_do_dia, eventos):
    """Lista do dia em ordem de horário. tarefas_do_dia e eventos vêm do servidor (já lidos)."""
    wd = date.fromisoformat(d_iso).weekday()
    fe, au = feitos(vault, d_iso), _auto(vault, d_iso)
    out = []
    for it in itens(vault):
        if wd not in it['dias']:
            continue
        auto = False
        lg = it['liga'] or ''
        if lg.startswith('agua:'):
            auto = au.get('agua', 0) >= int(lg.split(':')[1])
        elif lg:
            auto = bool(au.get(lg))
        manual = it['id'] in fe
        desmarcado = ('-' + it['id']) in fe
        out.append({'tipo': 'rotina', 'id': it['id'], 'hora': it['hora'], 'texto': it['texto'], 'liga': it['liga'],
                    'feito': manual or (auto and not desmarcado), 'auto': auto and not manual and not desmarcado,
                    'quando': fe.get(it['id'])})
    for t in tarefas_do_dia:
        out.append(dict(t, tipo='tarefa'))
    for e in eventos or []:
        eid = _id_evento(e[1])
        out.append({'tipo': 'evento', 'hora': '' if e[0] == 'dia todo' else e[0][:5], 'texto': e[1], 'cor': e[2] if len(e) > 2 else '',
                    'id': eid, 'feito': eid in fe and ('-' + eid) not in fe})
    out.sort(key=lambda x: (x['hora'] == '', x['hora'] or '99', {'evento': 0, 'tarefa': 1, 'rotina': 2}[x['tipo']]))
    return {'dia': d_iso, 'itens': out, 'arquivo': ARQ, 'agua': agua_estado(vault, d_iso, au.get('agua', 0)),
            'feitos': sum(1 for x in out if x.get('feito') and x['tipo'] != 'evento'), 'total': sum(1 for x in out if x['tipo'] != 'evento')}
