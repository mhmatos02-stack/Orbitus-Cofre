# -*- coding: utf-8 -*-
"""Orbitus — gestão de tarefas: criar, editar, acompanhar, remover (com desfazer), repetir e sugerir.

Fonte única: os .md de <cofre>/10_Tarefas, no formato do plugin Tasks do Obsidian.
  - [ ] Título — contexto 🔺 🔁 every week 📅 2026-11-06 ⏰ 10:00 🔗 https://… #trabalho #fazendo ➕ 2026-10-31
Área = tag (#pessoal #trabalho #financas #saude #viagem). Situação = tag #fazendo ou #aguardando (sem tag = a fazer).
Remover = a linha vira "- [-] … 🗑 data" na seção "## Arquivo" do Tarefas.md (o Tasks entende como cancelada). Desfazer devolve.
Sugestões dos agentes: nunca viram tarefa sozinhas; o que você aceita ou dispensa fica em 00_Sistema/tarefas_sugestoes.json.
"""
import calendar, hashlib, json, os, re, threading, unicodedata
from datetime import date, datetime, timedelta

TRAVA = threading.Lock()
TASK_RE = re.compile(r'^(\s*[-*] \[)([ xX\-])(\] )(.*)$')
PRIO = {'🔺': 0, '⏫': 1, '🔼': 2, '🔽': 4}
PRIO_INV = {0: '🔺', 1: '⏫', 2: '🔼', 4: '🔽'}
AREAS = {'financas': 'Finanças', 'finanças': 'Finanças', 'wealth': 'Finanças', 'saude': 'Saúde', 'saúde': 'Saúde', 'treino': 'Saúde',
         'viagem': 'Viagem', 'trabalho': 'Trabalho', 'vik': 'Trabalho', 'pessoal': 'Pessoal'}
AREA_TAG = {'Finanças': '#financas', 'Saúde': '#saude', 'Viagem': '#viagem', 'Trabalho': '#trabalho', 'Pessoal': '#pessoal'}
STATUS = ('fazendo', 'aguardando')
REPETE = {'': '', 'every day': 'Todo dia', 'every weekday': 'Dias úteis', 'every week': 'Toda semana',
          'every month': 'Todo mês', 'every year': 'Todo ano'}
WD_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
WD_PT = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']
TOKEN = re.compile(r'(🔺|⏫|🔼|🔽|🔁|📅|⏰|🔗|➕|✅|🛫|⏳|🗑)')


def _sa(t):
    return re.sub(r'[̀-ͯ]', '', unicodedata.normalize('NFD', str(t or '').lower()))


# ------------------------------------------------------------------ linha <-> campos
def ler_linha(linha):
    m = TASK_RE.match(linha)
    if not m:
        return None
    corpo = m.group(4)
    f = {'marca': m.group(2).lower(), 'feito': m.group(2).lower() == 'x', 'cancelada': m.group(2) == '-'}
    f['prio'] = min([PRIO[e] for e in PRIO if e in corpo] or [3])

    def campo(sim, rx=r'(\d{4}-\d{2}-\d{2})'):
        mm = re.search(re.escape(sim) + r'\s*' + rx, corpo)
        return mm.group(1) if mm else ''
    f['due'] = campo('📅')
    f['hora'] = campo('⏰', r'(\d{1,2}:\d{2})')
    f['criada'] = campo('➕')
    f['feita_em'] = campo('✅')
    f['removida_em'] = campo('🗑')
    mm = re.search(r'🔗\s*(\S+)', corpo)
    f['url'] = mm.group(1) if mm else ''
    mm = re.search(r'🔁\s*([^🔺⏫🔼🔽📅⏰🔗➕✅🛫⏳🗑#]+)', corpo)
    f['repete'] = mm.group(1).strip() if mm else ''
    tags = [t.lower() for t in re.findall(r'(?:^|\s)#([\w\-/À-ÿ]+)', corpo)]
    f['area'] = next((AREAS[t] for t in tags if t in AREAS), 'Pessoal')
    f['status'] = next((t for t in tags if t in STATUS), '')
    f['tags_extra'] = [t for t in tags if t not in AREAS and t not in STATUS]
    t = corpo
    t = re.sub(r'🔗\s*\S+', '', t)
    t = re.sub(r'🔁\s*[^🔺⏫🔼🔽📅⏰🔗➕✅🛫⏳🗑#]+', '', t)
    t = re.sub(r'(📅|➕|✅|🛫|⏳|🗑)\s*\d{4}-\d{2}-\d{2}', '', t)
    t = re.sub(r'⏰\s*\d{1,2}:\d{2}', '', t)
    t = re.sub(r'[🔺⏫🔼🔽]', '', t)
    t = re.sub(r'(^|\s)#[\w\-/À-ÿ]+', ' ', t)
    fonte = ''
    mm = re.search(r'\s[—–]\s(.+)$', t) or re.search(r'\s--?\s(.+)$', t)
    if mm:
        fonte, t = mm.group(1).strip(), t[:mm.start()]
    f['titulo'] = re.sub(r'\s+', ' ', t).strip()
    f['fonte'] = re.sub(r'\s+', ' ', fonte).strip()
    return f


def montar_linha(f, marca=' '):
    p = ['- [%s] %s' % (marca, re.sub(r'\s+', ' ', f['titulo']).strip())]
    if f.get('fonte'):
        p[0] += ' — ' + f['fonte']
    if f.get('prio', 3) in PRIO_INV:
        p.append(PRIO_INV[f['prio']])
    if f.get('repete'):
        p.append('🔁 ' + f['repete'])
    if f.get('due'):
        p.append('📅 ' + f['due'])
    if f.get('hora'):
        p.append('⏰ ' + f['hora'])
    if f.get('url'):
        p.append('🔗 ' + f['url'])
    p.append(AREA_TAG.get(f.get('area') or 'Pessoal', '#pessoal'))
    if f.get('status') in STATUS:
        p.append('#' + f['status'])
    p += ['#' + t for t in f.get('tags_extra') or []]
    if f.get('criada'):
        p.append('➕ ' + f['criada'])
    if marca == 'x' and f.get('feita_em'):
        p.append('✅ ' + f['feita_em'])
    if marca == '-' and f.get('removida_em'):
        p.append('🗑 ' + f['removida_em'])
    return ' '.join(p)


def _validar(f):
    t = re.sub(r'[\r\n]+', ' ', str(f.get('titulo') or '')).strip()
    if not t:
        raise ValueError('escreva o que fazer')
    if TOKEN.search(t) or re.search(r'(^|\s)#\w', t):
        t = TOKEN.sub('', t)
    f['titulo'] = t[:240]
    f['fonte'] = re.sub(r'[\r\n]+', ' ', str(f.get('fonte') or '')).strip()[:160]
    for k, rx in (('due', r'^\d{4}-\d{2}-\d{2}$'), ('hora', r'^\d{2}:\d{2}$'), ('criada', r'^\d{4}-\d{2}-\d{2}$')):
        v = str(f.get(k) or '').strip()
        if v and not re.match(rx, v):
            raise ValueError('%s inválido: %s' % (k, v))
        f[k] = v
    f['prio'] = int(f.get('prio', 3)) if str(f.get('prio', 3)) in ('0', '1', '2', '3', '4') else 3
    f['area'] = f.get('area') if f.get('area') in AREA_TAG else 'Pessoal'
    f['status'] = f.get('status') if f.get('status') in STATUS else ''
    r = str(f.get('repete') or '').strip()
    if r and not re.match(r'^every (day|weekday|week|month|year)( on (%s))?$' % '|'.join(WD_EN), r):
        raise ValueError('repetição inválida')
    if r and not f['due']:
        f['due'] = date.today().isoformat()
    f['repete'] = r
    u = str(f.get('url') or '').strip()
    f['url'] = u if re.match(r'^https?://\S+$', u) else ''
    f['tags_extra'] = [t for t in (f.get('tags_extra') or []) if re.match(r'^[\w\-/À-ÿ]{1,40}$', t)]
    return f


# ------------------------------------------------------------------ repetição
def proxima(due, regra):
    d = date.fromisoformat(due) if due else date.today()
    if regra.startswith('every day'):
        return d + timedelta(days=1)
    if regra.startswith('every weekday'):
        n = d + timedelta(days=1)
        while n.weekday() > 4:
            n += timedelta(days=1)
        return n
    if regra.startswith('every week'):
        m = re.search(r' on (\w+)', regra)
        if m and m.group(1) in WD_EN:
            alvo = WD_EN.index(m.group(1))
            n = d + timedelta(days=1)
            while n.weekday() != alvo:
                n += timedelta(days=1)
            return n
        return d + timedelta(days=7)
    if regra.startswith('every month'):
        a, mm = (d.year + (d.month // 12), d.month % 12 + 1)
        return date(a, mm, min(d.day, calendar.monthrange(a, mm)[1]))
    if regra.startswith('every year'):
        try:
            return d.replace(year=d.year + 1)
        except ValueError:
            return d.replace(year=d.year + 1, day=28)
    return None


# ------------------------------------------------------------------ arquivo
def _arq_principal(vault):
    return os.path.join(vault, '10_Tarefas', 'Tarefas.md')


def _caminho(vault, arquivo):
    p = os.path.normpath(os.path.join(vault, arquivo))
    if not p.startswith(os.path.join(vault, '10_Tarefas')) or not p.endswith('.md'):
        raise ValueError('arquivo fora de 10_Tarefas')
    return p


def _ler(p):
    try:
        with open(p, encoding='utf-8') as f:
            return f.read().split('\n')
    except OSError:
        return []


def _gravar(p, linhas):
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(linhas))
    os.replace(tmp, p)


def _secao(linhas, nome, criar=True):
    """Índice onde inserir a próxima linha da seção (depois das tarefas que já estão lá)."""
    try:
        i = next(k for k, l in enumerate(linhas) if l.strip().lower() == '## ' + nome.lower()) + 1
    except StopIteration:
        if not criar:
            return None
        while linhas and linhas[-1].strip() == '':
            linhas.pop()
        linhas += ['', '## ' + nome, '']
        return len(linhas)
    while i < len(linhas) and linhas[i].strip() == '':
        i += 1
    while i < len(linhas) and TASK_RE.match(linhas[i]):
        i += 1
    return i


def _conferir(linhas, linha, texto):
    if linha >= len(linhas) or linhas[linha] != texto:
        raise ValueError('a tarefa mudou no Obsidian; recarregue o painel')


def criar(vault, corpo):
    f = _validar(dict(corpo))
    f['criada'] = date.today().isoformat()
    linha = montar_linha(f)
    p = _arq_principal(vault)
    with TRAVA:
        linhas = _ler(p) or ['# Tarefas', '', '## Inbox', '']
        i = _secao(linhas, 'Inbox')
        linhas.insert(i, linha)
        _gravar(p, linhas)
    return {'ok': True, 'linha': linha, 'resumo': resumo(f)}


def editar(vault, corpo):
    p = _caminho(vault, corpo.get('arquivo', ''))
    with TRAVA:
        linhas = _ler(p)
        n, texto = int(corpo.get('linha', -1)), corpo.get('texto', '')
        _conferir(linhas, n, texto)
        atual = ler_linha(texto)
        if not atual:
            raise ValueError('linha não é tarefa')
        novo = dict(atual)
        for k in ('titulo', 'fonte', 'due', 'hora', 'prio', 'area', 'status', 'repete', 'url'):
            if k in (corpo.get('campos') or {}):
                novo[k] = corpo['campos'][k]
        novo = _validar(novo)
        linhas[n] = montar_linha(novo, 'x' if atual['feito'] else ' ')
        _gravar(p, linhas)
    return {'ok': True, 'texto': linhas[n]}


def remover(vault, corpo):
    """Tira do lugar e guarda em '## Arquivo' como cancelada (🗑 hoje). Devolve a linha arquivada para desfazer."""
    p = _caminho(vault, corpo.get('arquivo', ''))
    pa = _arq_principal(vault)
    with TRAVA:
        linhas = _ler(p)
        n, texto = int(corpo.get('linha', -1)), corpo.get('texto', '')
        _conferir(linhas, n, texto)
        f = ler_linha(texto)
        if not f:
            raise ValueError('linha não é tarefa')
        f['removida_em'] = date.today().isoformat()
        arq = montar_linha(f, '-')
        del linhas[n]
        if p == pa:
            alvo = linhas
        else:
            _gravar(p, linhas)
            alvo = _ler(pa)
        i = _secao(alvo, 'Arquivo')
        alvo.insert(i, arq)
        _gravar(pa, alvo)
    return {'ok': True, 'arquivada': arq}


def restaurar(vault, corpo):
    texto = corpo.get('arquivada', '')
    pa = _arq_principal(vault)
    with TRAVA:
        linhas = _ler(pa)
        try:
            n = linhas.index(texto)
        except ValueError:
            raise ValueError('não achei essa tarefa no Arquivo')
        f = ler_linha(texto)
        f['removida_em'] = ''
        del linhas[n]
        i = _secao(linhas, 'Inbox')
        linhas.insert(i, montar_linha(f, ' '))
        _gravar(pa, linhas)
    return {'ok': True}


def concluir_com_repeticao(linhas, n, hoje_iso):
    """Chamado ao marcar como feita: se a tarefa repete, insere a próxima ocorrência logo acima (como o Tasks faz)."""
    f = ler_linha(linhas[n])
    if not f or not f['repete']:
        return None
    prox = proxima(f['due'], f['repete'])
    if not prox:
        return None
    nf = dict(f, due=prox.isoformat(), criada=hoje_iso, feita_em='', status='')
    nova = montar_linha(nf, ' ')
    linhas.insert(n, nova)
    return nova


# ------------------------------------------------------------------ acompanhar
def _todas(vault):
    out = []
    for raiz, _, arqs in os.walk(os.path.join(vault, '10_Tarefas')):
        for a in sorted(arqs):
            if a.endswith('.md'):
                p = os.path.join(raiz, a)
                for i, l in enumerate(_ler(p)):
                    f = ler_linha(l)
                    if f:
                        f.update(arquivo=os.path.relpath(p, vault), linha=i, texto=l)
                        out.append(f)
    return out


def historico(vault, dias=30):
    hoje = date.today()
    seg = (hoje - timedelta(days=hoje.weekday())).isoformat()
    ini = (hoje - timedelta(days=dias)).isoformat()
    T = _todas(vault)
    feitas = sorted([t for t in T if t['feito'] and t['feita_em'] >= ini], key=lambda t: t['feita_em'], reverse=True)
    arquivo = sorted([t for t in T if t['cancelada']], key=lambda t: t['removida_em'], reverse=True)[:60]
    abertas = [t for t in T if not t['feito'] and not t['cancelada']]
    placar = {'feitas_semana': sum(1 for t in T if t['feito'] and t['feita_em'] >= seg),
              'criadas_semana': sum(1 for t in T if t['criada'] and t['criada'] >= seg and not t['cancelada']),
              'abertas': len(abertas),
              'atrasadas': sum(1 for t in abertas if t['due'] and t['due'] < hoje.isoformat()),
              'fazendo': sum(1 for t in abertas if t['status'] == 'fazendo'),
              'aguardando': sum(1 for t in abertas if t['status'] == 'aguardando')}
    return {'feitas': feitas, 'arquivo': arquivo, 'placar': placar}


def resumo(f):
    s = f['titulo']
    if f.get('due'):
        d = date.fromisoformat(f['due'])
        hoje = date.today()
        s += ' · ' + ('hoje' if d == hoje else 'amanhã' if d == hoje + timedelta(days=1) else WD_PT[d.weekday()] + ' ' + d.strftime('%d/%m'))
    if f.get('hora'):
        s += ' às ' + f['hora']
    if f.get('repete'):
        s += ' · ' + REPETE.get(re.sub(r' on \w+$', '', f['repete']), f['repete']).lower()
    return s


# ------------------------------------------------------------------ captura em linguagem natural (Siri, Compartilhar, campo rápido)
MESES = {'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12}
PREP = r'(?:(?:na|no|nesta|neste|esta|este|pr[oó]xim[ao]|para|pra|at[eé]|em|de|dia)\s+)*'


def interpretar(texto, hoje=None):
    """'ligar para o contador sexta 10h urgente' -> título, data, hora, prioridade, repetição, área."""
    hoje = hoje or date.today()
    t = ' ' + re.sub(r'\s+', ' ', str(texto or '')).strip() + ' '
    f = {'titulo': '', 'due': '', 'hora': '', 'prio': 3, 'repete': '', 'area': '', 'url': ''}
    m = re.search(r'https?://\S+', t)
    if m:
        f['url'] = m.group(0).rstrip('.,)')
        t = t.replace(m.group(0), ' ')

    def tira(rx, flags=re.I):
        nonlocal t
        m = re.search(rx, t, flags)
        if m:
            t = t[:m.start()] + ' ' + t[m.end():]
        return m
    # repetição
    m = tira(r'\s(?:tod[oa]s?\s+(?:as\s+|os\s+)?)(segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)s?(?:-feiras?)?(?=\s)')
    if m:
        wd = [_sa(x)[:3] for x in WD_PT].index(_sa(m.group(1))[:3])
        f['repete'] = 'every week on ' + WD_EN[wd]
        n = hoje
        while n.weekday() != wd:
            n += timedelta(days=1)
        f['due'] = n.isoformat()
    elif tira(r'\s(?:todo\s+dia|todos\s+os\s+dias|diariamente)(?=\s)'):
        f['repete'] = 'every day'
    elif tira(r'\s(?:dias?\s+[uú]teis|de\s+segunda\s+a\s+sexta)(?=\s)'):
        f['repete'] = 'every weekday'
    elif tira(r'\s(?:toda\s+semana|semanalmente)(?=\s)'):
        f['repete'] = 'every week'
    elif tira(r'\s(?:todo\s+m[eê]s|mensalmente)(?=\s)'):
        f['repete'] = 'every month'
    elif tira(r'\s(?:todo\s+ano|anualmente)(?=\s)'):
        f['repete'] = 'every year'
    # prioridade
    if tira(r'\s(?:urgente|urg[eê]ncia)(?=\s)'):
        f['prio'] = 0
    elif tira(r'\s(?:importante|prioridade alta)(?=\s)'):
        f['prio'] = 1
    # hora
    m = tira(r'\s(?:[àa]s\s+|@\s*)?(\d{1,2})(?::(\d{2})|h(\d{2})?)(?=\s)') or tira(r'\s[àa]s\s+(\d{1,2})()()(?=\s)')
    if m:
        h, mi = int(m.group(1)), m.group(2) or m.group(3) or '00'
        if h < 24 and int(mi) < 60:
            f['hora'] = '%02d:%s' % (h, mi)
    # data
    if not f['due']:
        if tira(r'\s' + PREP + r'depois\s+de\s+amanh[aã](?=\s)'):
            f['due'] = (hoje + timedelta(days=2)).isoformat()
        elif tira(r'\s' + PREP + r'amanh[aã](?=\s)'):
            f['due'] = (hoje + timedelta(days=1)).isoformat()
        elif tira(r'\s' + PREP + r'hoje(?=\s)'):
            f['due'] = hoje.isoformat()
        elif tira(r'\s' + PREP + r'(?:semana\s+que\s+vem|pr[oó]xima\s+semana)(?=\s)'):
            f['due'] = (hoje + timedelta(days=7 - hoje.weekday())).isoformat()
        else:
            m = tira(r'\s' + PREP + r'(segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)(?:-feira)?(?=\s)')
            if m:
                wd = [_sa(x)[:3] for x in WD_PT].index(_sa(m.group(1))[:3])
                n = hoje + timedelta(days=1)
                while n.weekday() != wd:
                    n += timedelta(days=1)
                f['due'] = n.isoformat()
            else:
                m = tira(r'\s' + PREP + r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?=\s)')
                if m:
                    d, mo = int(m.group(1)), int(m.group(2))
                    a = int(m.group(3)) if m.group(3) else hoje.year
                    a += 2000 if a < 100 else 0
                    try:
                        x = date(a, mo, d)
                        if not m.group(3) and x < hoje - timedelta(days=30):
                            x = date(a + 1, mo, d)
                        f['due'] = x.isoformat()
                    except ValueError:
                        pass
                else:
                    m = tira(r'\s' + PREP + r'dia\s+(\d{1,2})(?:\s+de\s+([a-zç]{3})[a-zç]*)?(?=\s)')
                    if m:
                        d = int(m.group(1))
                        mo = MESES.get(_sa(m.group(2) or '')[:3]) if m.group(2) else None
                        try:
                            if mo:
                                x = date(hoje.year, mo, d)
                                if x < hoje - timedelta(days=30):
                                    x = date(hoje.year + 1, mo, d)
                            else:
                                x = date(hoje.year, hoje.month, d)
                                if x < hoje:
                                    a, mm = (hoje.year + (hoje.month // 12), hoje.month % 12 + 1)
                                    x = date(a, mm, d)
                            f['due'] = x.isoformat()
                        except ValueError:
                            pass
                    else:
                        m = tira(r'\s(?:em|daqui\s+a)\s+(\d{1,2})\s+dias?(?=\s)')
                        if m:
                            f['due'] = (hoje + timedelta(days=int(m.group(1)))).isoformat()
    if f['hora'] and not f['due']:
        f['due'] = hoje.isoformat()
    if f['due']:   # sobrou uma data repetida ("sexta dia 06/11")? sai do título
        tira(r'\s(?:dia\s+)?\d{1,2}/\d{1,2}(?:/\d{2,4})?(?=\s)')
    # área por tag escrita ou palavra-chave
    m = tira(r'\s#(pessoal|trabalho|financas|finanças|saude|saúde|viagem|vik|wealth)(?=\s)')
    if m:
        f['area'] = AREAS[m.group(1).lower()]
    t = re.sub(r'^\s*(?:anota(?:r)?|lembra(?:r)?(?:\s+de)?|me\s+lembra(?:\s+de)?|criar?\s+tarefa|tarefa)\s*:?\s*', ' ', t, flags=re.I)
    t = re.sub(r'\s+(?:na|no|para|pra|em|de|às|as|até)\s*$', '', t.strip(), flags=re.I)
    f['titulo'] = re.sub(r'\s+', ' ', t).strip(' ,.;:-')
    f['titulo'] = f['titulo'][:1].upper() + f['titulo'][1:]
    if not f['area']:
        s = _sa(f['titulo'])
        f['area'] = ('Finanças' if re.search(r'\b(banco|boleto|fatura|imposto|ir\b|invest|aporte|extrato|pix|pagar|conta de|carteira|acao|acoes|fii)', s)
                     else 'Saúde' if re.search(r'\b(treino|medico|dentista|exame|academia|vitamina|consulta)', s)
                     else 'Viagem' if re.search(r'\b(viagem|voo|mala|passaporte|hotel|check-?in)', s)
                     else 'Pessoal')
    return f


# ------------------------------------------------------------------ sugestões dos agentes
def _sug_arq(vault):
    return os.path.join(vault, '00_Sistema', 'tarefas_sugestoes.json')


def _sug_estado(vault):
    try:
        with open(_sug_arq(vault), encoding='utf-8') as f:
            j = json.load(f)
        return j if isinstance(j, dict) else {}
    except (OSError, ValueError):
        return {}


def _palavras(t):
    return {w for w in re.findall(r'[a-z0-9]{4,}', _sa(t))}


def _parecida(a, conjunto):
    pa = _palavras(a)
    if not pa:
        return False
    for pb in conjunto:
        if not pb:
            continue
        inter = len(pa & pb)
        if inter / len(pa | pb) >= .5 or inter / min(len(pa), len(pb)) >= .75:
            return True
    return False


def _sid(origem, chave):
    return hashlib.sha1((origem + '|' + _sa(chave)).encode('utf-8')).hexdigest()[:12]


def sugestoes(vault, d, mesa_saude=None):
    """d = dados() do servidor. Junta o que os agentes e sistemas pedem de você e ainda não virou tarefa."""
    hoje = date.today().isoformat()
    est = _sug_estado(vault)
    existentes = [_palavras(t['titulo']) for t in _todas(vault)]
    cand = []

    def add(origem, titulo, area, due='', fonte='', motivo='', prio=3, chave=None, dedup=True):
        titulo = re.sub(r'\s+', ' ', str(titulo or '')).strip()
        if not titulo or len(titulo) < 4:
            return
        sid = _sid(origem, chave or titulo)
        if sid in est or (dedup and _parecida(titulo, existentes)) or any(c['id'] == sid for c in cand):
            return
        cand.append({'id': sid, 'origem': origem, 'titulo': titulo[:200], 'area': area, 'due': due or '', 'fonte': fonte,
                     'motivo': motivo, 'prio': prio})

    # Mesa do Wealth: só passos do plano que o Wealth liberou (os bloqueados ficam "na fila" na Home e na Mesa)
    import wealth_plano
    mh = d.get('mesa_home') or {}
    for p in mh.get('proximos_passos') or []:
        if not p.get('liberada'):
            continue
        add('Mesa do Wealth', wealth_plano.titulo(p), 'Finanças', max((p.get('inicio') or '')[:10], hoje) if p.get('inicio') else '',
            'Mesa do Wealth · plano ' + str(p.get('id')), wealth_plano.motivo(p), 1 if p.get('tipo') == 'ordem' else 2, 'plano:' + str(p.get('id')))
    # tarefas do plano marcadas feitas aqui, mas que o Wealth ainda não sabe
    for x in mh.get('feitas_sem_registro') or []:
        add('Mesa do Wealth', 'Confirmar ao Wealth: ' + str(x.get('acao')), 'Finanças', hoje, 'Mesa do Wealth · plano ' + str(x.get('passo')),
            'Você marcou como feito no Tarefas em %s, mas o Wealth ainda mostra pendente. Aceitar = avisar o Wealth que executou '
            '(ele confere no razão às 20h47 e pede a nota). Se não executou, dispense e desmarque a tarefa.' % wealth_plano._br(x.get('feita_em')),
            0, 'confirmar:' + str(x.get('passo')), dedup=False)
        sid = _sid('Mesa do Wealth', 'confirmar:' + str(x.get('passo')))
        for c in cand:
            if c['id'] == sid:
                c['plano_feito'] = x.get('passo')
    for dc in mh.get('abertas') or []:
        if ('decisao:' + str(dc.get('id'))) in (mh.get('respostas') or {}):
            continue
        add('Mesa do Wealth', 'Responder na Mesa: ' + (dc.get('titulo') or dc.get('pergunta') or ''), 'Finanças',
            (dc.get('prazo') or '')[:10], 'Mesa do Wealth · decisão', dc.get('pergunta') or '', 1, 'decisao:' + str(dc.get('id')))
    # e-mails que pedem resposta
    em = d.get('emails') or {}
    for e in (em.get('itens') or [])[:8]:
        add('E-mails', 'Responder %s: %s' % (e.get('de') or '?', e.get('assunto') or ''), 'Pessoal', hoje,
            'e-mail · ' + (e.get('conta') or ''), (e.get('previa') or '')[:140], 3, 'mail:' + str(e.get('mid') or e.get('assunto')))
    # Mesa da Saúde: tarefas propostas no parecer (ou os ajustes, se o parecer não trouxer tarefas)
    par = (mesa_saude or {}).get('ultimo_parecer') or {}
    for aid, o in (par.get('agentes') or {}).items():
        nome = {'personal': 'Personal trainer', 'nutricionista': 'Nutricionista', 'nutri': 'Nutricionista'}.get(aid, aid)
        itens = o.get('tarefas') or []
        for it in itens[:4]:
            if isinstance(it, dict):
                add('Mesa da Saúde', it.get('titulo'), 'Saúde', it.get('data') or '', nome, it.get('porque') or '', 3, aid + ':' + str(it.get('titulo')))
            else:
                add('Mesa da Saúde', it, 'Saúde', '', nome, '', 3, aid + ':' + str(it))
    # viagens: alertas
    for a in d.get('viagem_alertas') or []:
        add('Viagem', a.get('texto'), 'Viagem', '', a.get('origem') or 'Viagem', '', 1 if a.get('urgente') else 3, 'viagem:' + str(a.get('texto')))
    # saúde das rotinas do Orbitus
    for f in d.get('federacao') or []:
        for x in f.get('falhas') or []:
            add('Orbitus', 'Verificar: ' + x, 'Pessoal', hoje, f.get('nome') or 'Orbitus', '', 2, 'falha:' + x[:60])
    ordem = {'Mesa do Wealth': 0, 'Viagem': 1, 'Mesa da Saúde': 2, 'E-mails': 3, 'Orbitus': 4}
    cand.sort(key=lambda c: (c['prio'], ordem.get(c['origem'], 9), c['due'] or '9999'))
    return cand


def responder_sugestao(vault, corpo, cand):
    sid, acao = str(corpo.get('id') or ''), corpo.get('acao')
    c = next((x for x in cand if x['id'] == sid), None)
    if not c:
        raise ValueError('sugestão não encontrada (talvez já tenha virado tarefa)')
    if acao not in ('aceitar', 'dispensar'):
        raise ValueError('ação inválida')
    out = {'ok': True}
    if acao == 'aceitar' and c.get('plano_feito'):
        import mesa
        mesa.responder(vault, {'tipo': 'plano', 'id': c['plano_feito'], 'acao': 'feito',
                               'nota': 'confirmado pelo Tarefas do Orbitus; a nota de corretagem vai para a pasta Entrada'})
    elif acao == 'aceitar':
        campos = dict(c)
        campos.update({k: v for k, v in (corpo.get('campos') or {}).items() if k in ('titulo', 'due', 'hora', 'prio', 'area')})
        campos['fonte'] = 'sugerido por ' + c['origem'] + (' · ' + c['fonte'] if c['fonte'] and c['fonte'] != c['origem'] else '')
        out = criar(vault, campos)
    p = _sug_arq(vault)
    with TRAVA:
        est = _sug_estado(vault)
        est[sid] = {'acao': acao, 'em': datetime.now().isoformat(timespec='minutes'), 'titulo': c['titulo'][:120], 'origem': c['origem']}
        if len(est) > 800:
            est = dict(sorted(est.items(), key=lambda kv: kv[1].get('em', ''))[-600:])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(est, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    return out


# ------------------------------------------------------------------ eventos sociais: presente + conflito de agenda
EVENTO_SOCIAL = re.compile(r'\b(anivers[aá]rio|niver|casamento|ch[aá] de (?:beb[eê]|panela|fralda|cozinha)|batizado|formatura|bodas)\b', re.I)


def pessoa_do_evento(titulo):
    t = re.sub(r'^\s*(?:festa\s+de\s+)?', '', titulo, flags=re.I)
    m = re.search(r'(?:anivers[aá]rio|niver|casamento|batizado|formatura|ch[aá] de \w+|bodas)\s+(?:d[aoe]s?\s+)?(.+)$', t, re.I)
    if not m:
        return ''
    p = re.split(r'\s+(?:no|na|em|às|as|dia)\s+', m.group(1).strip(), maxsplit=1)[0]
    return p.strip(' ,.;:-')[:60]


def tarefas_do_evento(f, hoje=None):
    """Para aniversário, casamento etc.: devolve a tarefa de comprar presente, uns dias antes."""
    hoje = hoje or date.today()
    if not f.get('due') or not EVENTO_SOCIAL.search(f.get('titulo') or ''):
        return []
    ev = date.fromisoformat(f['due'])
    quem = pessoa_do_evento(f['titulo'])
    alvo = ev - timedelta(days=3)
    if alvo < hoje:
        alvo = max(hoje, ev - timedelta(days=1)) if ev > hoje else hoje
    prep = 'para a' if re.match(r'^[A-ZÁÉÍÓÚ][a-záéíóúãõç]+a\b', quem or '') else 'para o' if quem and not ' e ' in quem else 'para'
    titulo = ('Comprar presente %s %s' % (prep, quem)).strip() if quem else 'Comprar presente'
    return [{'titulo': titulo, 'due': alvo.isoformat(), 'area': f.get('area') or 'Pessoal', 'prio': 2,
             'fonte': '%s · %s' % (f['titulo'][:60], ev.strftime('%d/%m'))}]


def conflitos(d_iso, hora, eventos_do_dia, tarefas_do_dia, ignorar=''):
    """O que já ocupa esse dia (e, com hora, a janela de 2 h antes a 3 h depois)."""
    def mins(h):
        try:
            return int(h[:2]) * 60 + int(h[3:5])
        except (ValueError, TypeError):
            return None
    alvo = mins(hora) if hora else None
    out = []
    for e in eventos_do_dia or []:
        h = '' if e[0] == 'dia todo' else e[0][:5]
        m = mins(h) if h else None
        if alvo is None or m is None or alvo - 120 <= m <= alvo + 180:
            out.append({'hora': h or 'dia todo', 'texto': e[1], 'tipo': 'agenda'})
    for t in tarefas_do_dia or []:
        if t.get('feito') or _sa(t.get('texto', '')) == _sa(ignorar):
            continue
        m = mins(t.get('hora') or '')
        if m is not None and (alvo is None or alvo - 120 <= m <= alvo + 180):
            out.append({'hora': t['hora'], 'texto': t['texto'], 'tipo': 'tarefa'})
    return out
