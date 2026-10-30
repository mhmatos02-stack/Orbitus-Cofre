# -*- coding: utf-8 -*-
"""Orbitus — Viagens: uma pasta por viagem em <Orbitus>/30_Viagens/<nome>/.

Cada pasta tem:
  roteiro.json   paradas, trechos, mapa, documentos, bagagem (o app só grava documentos e bagagem)
  Lista.md       lista editável no formato do plugin Tasks (também editável no Obsidian)
  Documentos/    arquivos da viagem (PDF de passagem, reserva, seguro...), servidos só para leitura

Toda gravação é feita sob trava e confere que o item não mudou desde a leitura.
"""
import json, mimetypes, os, re, threading
from datetime import date, datetime

TRAVA = threading.Lock()
TASK = re.compile(r'^(\s*[-*] \[)([ xX])(\] )(.*)$')
DUE = re.compile(r'📅\s*(\d{4}-\d{2}-\d{2})')
DONE = re.compile(r'\s*✅\s*\d{4}-\d{2}-\d{2}')


def _raiz(vault):
    return os.path.join(vault, '30_Viagens')


def _pasta(vault, nome):
    raiz = os.path.normpath(_raiz(vault))
    p = os.path.normpath(os.path.join(raiz, nome or ''))
    if not nome or os.path.dirname(p) != raiz or not os.path.isdir(p):
        raise ValueError('viagem inválida')
    return p


def _rot(p):
    with open(os.path.join(p, 'roteiro.json'), encoding='utf-8') as f:
        return json.load(f)


def _gravar_rot(p, r):
    tmp = os.path.join(p, '.roteiro.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(json.dumps(r, ensure_ascii=False, indent=1))
    os.replace(tmp, os.path.join(p, 'roteiro.json'))


def listar(vault):
    out, raiz = [], _raiz(vault)
    for n in sorted(os.listdir(raiz)) if os.path.isdir(raiz) else []:
        p = os.path.join(raiz, n)
        if not os.path.isfile(os.path.join(p, 'roteiro.json')):
            continue
        try:
            r = _rot(p)
        except (OSError, ValueError):
            continue
        out.append({'id': n, 'titulo': r.get('aba') or r.get('titulo') or n, 'de': r.get('de', ''), 'ate': r.get('ate', '')})
    hoje = date.today().isoformat()
    out.sort(key=lambda v: (bool(v['ate']) and v['ate'] < hoje, v['de'] or '9999'))   # as que já passaram vão para o fim
    return out


# ---------------------------------------------------------------- lista
def _ler_linhas(p):
    try:
        with open(os.path.join(p, 'Lista.md'), encoding='utf-8') as f:
            return f.read().split('\n')
    except OSError:
        return ['# Lista', '', '## Outros', '']


def _gravar_linhas(p, linhas):
    tmp = os.path.join(p, '.Lista.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(linhas))
    os.replace(tmp, os.path.join(p, 'Lista.md'))


def lista(p):
    secao, out = 'Outros', []
    for i, l in enumerate(_ler_linhas(p)):
        if l.startswith('## '):
            secao = l[3:].strip()
            continue
        m = TASK.match(l)
        if not m:
            continue
        corpo = m.group(4)
        due = DUE.search(corpo)
        t = DONE.sub('', DUE.sub('', corpo)).strip()
        nota = ''
        mm = re.search(r'\s[—–]\s(.+)$', t)
        if mm:
            nota, t = mm.group(1).strip(), t[:mm.start()].strip()
        out.append({'linha': i, 'texto': l, 'secao': secao, 'titulo': t, 'nota': nota,
                    'due': due.group(1) if due else '', 'feito': m.group(2).lower() == 'x'})
    return out


# ---------------------------------------------------------------- documentos
def _docs(r):
    return [d if isinstance(d, dict) else {'nome': d, 'ok': False} for d in r.get('documentos', [])]


def _arquivos(p):
    pasta = os.path.join(p, 'Documentos')
    if not os.path.isdir(pasta):
        return []
    return sorted(f for f in os.listdir(pasta) if not f.startswith('.') and f != 'LEIA-ME.md' and os.path.isfile(os.path.join(pasta, f)))


# ---------------------------------------------------------------- véspera
def vespera(r, lst, docs):
    """O que falta antes de sair: itens abertos com data até o dia da partida (ou sem data),
    documentos sem confirmação, bagagem a comprar e pontos a conferir."""
    de = r.get('de') or ''
    falta = []
    for i in lst:
        if not i['feito'] and (not i['due'] or not de or i['due'] <= de):
            falta.append({'tipo': 'lista', 'texto': i['titulo'] + (' — ' + i['nota'] if i['nota'] else ''), 'secao': i['secao']})
    for d in docs:
        if not d.get('ok'):
            falta.append({'tipo': 'documento', 'texto': d['nome']})
    b = r.get('bagagem')
    if b and b.get('precisa') and not b.get('comprada'):
        falta.append({'tipo': 'bagagem', 'texto': 'Comprar a mala de 23 kg · ' + b.get('voo', '')})
    for c in r.get('conferir', []):
        falta.append({'tipo': 'conferir', 'texto': c})
    dias = (date.fromisoformat(de) - date.today()).days if de else None
    return {'dias': dias, 'falta': falta, 'alerta': dias is not None and 0 <= dias <= 1}


def estado(vault, nome=None):
    vs = listar(vault)
    if not vs:
        return {'disponivel': False, 'erro': 'nenhuma viagem em 30_Viagens', 'viagens': []}
    if nome not in [v['id'] for v in vs]:
        nome = vs[0]['id']
    try:
        p = _pasta(vault, nome)
        r = _rot(p)
    except (OSError, ValueError) as e:
        return {'disponivel': False, 'erro': str(e), 'viagens': vs}
    lst, docs = lista(p), _docs(r)
    r.update(disponivel=True, id=nome, viagens=vs, lista=lst, documentos=docs, arquivos=_arquivos(p),
             secoes=[l[3:].strip() for l in _ler_linhas(p) if l.startswith('## ')] or ['Outros'],
             vespera=vespera(r, lst, docs))
    return r


def alertas(vault):
    """Para a Home: véspera de viagem (D-1 e D-0) e prazo da bagagem (a partir de 7 dias antes)."""
    out, hoje = [], date.today()
    for v in listar(vault):
        try:
            p = _pasta(vault, v['id'])
            r = _rot(p)
        except (OSError, ValueError):
            continue
        ves = vespera(r, lista(p), _docs(r))
        if ves['alerta'] and ves['falta']:
            out.append({'texto': 'Viagem %s: %d pendência(s) no checklist da véspera' % ('hoje' if ves['dias'] == 0 else 'amanhã', len(ves['falta'])),
                        'origem': v['titulo'], 'viagem': v['id'], 'urgente': True})
        b = r.get('bagagem') or {}
        if not (b.get('precisa') and not b.get('comprada') and b.get('prazo_antecipado')):
            continue
        try:
            prazo = datetime.fromisoformat(b['prazo_antecipado'])
            voo = date.fromisoformat(b.get('data_voo') or '9999-12-31')
        except ValueError:
            continue
        dias = (prazo.date() - hoje).days
        if voo < hoje or dias > 7:
            continue
        txt = ('Comprar a mala de 23 kg da volta até %s, %s' % (prazo.strftime('%d/%m'), prazo.strftime('%H:%M')) if dias >= 0
               else 'Mala de 23 kg ainda não comprada: o prazo do preço antecipado já passou')
        out.append({'texto': txt, 'origem': v['titulo'] + ' · ' + b.get('voo', ''), 'viagem': v['id'], 'urgente': dias <= 2})
    return out


def arquivo(vault, nome, f):
    pasta = os.path.join(_pasta(vault, nome), 'Documentos')
    alvo = os.path.normpath(os.path.join(pasta, f or ''))
    if not f or os.path.dirname(alvo) != pasta or not os.path.isfile(alvo):
        raise ValueError('arquivo inválido')
    with open(alvo, 'rb') as fh:
        return fh.read(), mimetypes.guess_type(alvo)[0] or 'application/octet-stream'


# ---------------------------------------------------------------- edição
def _limpo(s, n=200):
    return re.sub(r'[\r\n]+', ' ', str(s or '')).replace('—', '-').strip()[:n]


def _valor(s):
    s = str(s or '').replace('R$', '').strip()
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    v = float(s)
    if not 0 < v < 10000:
        raise ValueError('valor fora do esperado')
    return round(v, 2)


def _editar_roteiro(p, acao, corpo):
    r = _rot(p)
    docs = _docs(r)
    if acao == 'doc_adicionar':
        nome = _limpo(corpo.get('nome'), 140)
        if not nome:
            raise ValueError('escreva o documento')
        docs.append({'nome': nome, 'ok': False})
    elif acao in ('doc_alternar', 'doc_excluir'):
        i = int(corpo.get('indice', -1))
        if not (0 <= i < len(docs)) or docs[i]['nome'] != corpo.get('nome'):
            raise ValueError('a lista de documentos mudou; recarregue a página')
        if acao == 'doc_alternar':
            docs[i]['ok'] = not docs[i].get('ok')
        else:
            del docs[i]
    else:
        b = r.get('bagagem')
        if not b:
            raise ValueError('esta viagem não tem bagagem a comprar')
        if acao == 'bag_preco':
            try:
                v = _valor(corpo.get('valor'))
            except ValueError:
                raise ValueError('valor inválido: use algo como 189,90')
            b.setdefault('precos', []).append({'data': date.today().isoformat(), 'valor': v, 'nota': _limpo(corpo.get('nota'), 80)})
        elif acao == 'bag_comprada':
            b['comprada'] = not b.get('comprada')
            b['comprada_em'] = date.today().isoformat() if b['comprada'] else None
            if b['comprada'] and corpo.get('valor'):
                b['valor_pago'] = _valor(corpo['valor'])
            elif not b['comprada']:
                b.pop('valor_pago', None)
        else:
            raise ValueError('ação inválida')
    r['documentos'] = docs
    _gravar_rot(p, r)


def editar(vault, corpo):
    acao = corpo.get('acao')
    vs = listar(vault)
    p = _pasta(vault, corpo.get('viagem') or (vs[0]['id'] if vs else ''))
    with TRAVA:
        if acao in ('doc_alternar', 'doc_adicionar', 'doc_excluir', 'bag_preco', 'bag_comprada'):
            return _editar_roteiro(p, acao, corpo)
        linhas = _ler_linhas(p)
        if acao == 'adicionar':
            titulo = _limpo(corpo.get('titulo'), 160)
            if not titulo:
                raise ValueError('escreva o item')
            secao = _limpo(corpo.get('secao'), 60) or 'Outros'
            nota = _limpo(corpo.get('nota'), 200)
            data = corpo.get('data') or ''
            if data and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', data):
                raise ValueError('data inválida')
            nova = '- [ ] ' + titulo + (' — ' + nota if nota else '') + (' 📅 ' + data if data else '')
            hs = [k for k, l in enumerate(linhas) if l.strip() == '## ' + secao]
            if not hs:
                while linhas and linhas[-1].strip() == '':
                    linhas.pop()
                linhas += ['', '## ' + secao, '']
                hs = [len(linhas) - 2]
            h = hs[0]
            fim = next((k for k in range(h + 1, len(linhas)) if linhas[k].startswith('## ')), len(linhas))
            tarefas = [k for k in range(h + 1, fim) if TASK.match(linhas[k])]
            i = tarefas[-1] + 1 if tarefas else h + 1
            if not tarefas:
                linhas.insert(i, '')
                i += 1
            linhas.insert(i, nova)
        else:
            i, texto = int(corpo.get('linha', -1)), corpo.get('texto')
            if not (0 <= i < len(linhas)) or linhas[i] != texto or not TASK.match(texto):
                raise ValueError('a lista mudou no Obsidian; recarregue a página')
            if acao == 'alternar':
                m = TASK.match(texto)
                if m.group(2) == ' ':
                    linhas[i] = m.group(1) + 'x' + m.group(3) + m.group(4).rstrip() + ' ✅ ' + date.today().isoformat()
                else:
                    linhas[i] = m.group(1) + ' ' + m.group(3) + DONE.sub('', m.group(4)).rstrip()
            elif acao == 'excluir':
                del linhas[i]
            else:
                raise ValueError('ação inválida')
        _gravar_linhas(p, linhas)
