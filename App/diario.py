# -*- coding: utf-8 -*-
"""Orbitus — "Contar meu dia": você conta o dia em texto livre (ou falando) e a Vega transforma em registros.

Fluxo: entender(texto) -> plano com ações legíveis (nada é gravado) -> você confere e confirma -> aplicar(ações)
grava no Treino (refeições, passos, remo, água, sono, peso, cintura, treino, hábitos), marca a rotina do dia,
conclui tarefas e cria as novas. Cada aplicação guarda um "desfazer" em 00_Sistema/diario_desfazer/.

transcrever(wav) usa o Google Speech-to-Text (mesma chave do Google TTS, no Chaves) para o microfone novo.
"""
import base64, copy, hashlib, json, os, re, subprocess, time, urllib.error, urllib.request
from datetime import date, datetime

import concierge
import rotina
import treino

SLOTS = {'cafe': 'Café da manhã', 'almoco': 'Almoço', 'lanche': 'Lanche', 'jantar': 'Jantar'}
HABITOS = {'creatina': 'Creatina', 'caminhada': 'Movimento pós-refeição', 'jantar16': 'Jantar decidido'}
DATA = re.compile(r'^\d{4}-\d{2}-\d{2}$')

PROMPT = """Você é a Vega, assistente pessoal do Marcio no Orbitus. Ele vai contar o dia dele em texto livre (muitas vezes ditado, com erros de transcrição).
Sua tarefa é transformar o relato em registros estruturados. Não invente nada que ele não disse. Na dúvida, deixe de fora e cite em "nao_entendi".

Responda SOMENTE com um objeto JSON (sem crases, sem texto antes ou depois), neste formato:
{
 "fala": "1 a 3 frases curtas, calorosas, em português, dizendo o que você entendeu; se faltar algo importante (ex.: proteína muito abaixo da meta, refeição sem detalhe), termine com UMA pergunta curta",
 "refeicoes": [{"slot": "cafe|almoco|lanche|jantar", "itens": [{"f": "chave_do_alimento", "q": 150}], "outros": [{"n": "nome curto", "k": 350, "p": 20}]}],
 "passos": null, "remo_min": null, "agua_copos": null, "peso_kg": null, "cintura_cm": null, "sono_h": null,
 "treino_feito": null, "ioga": null, "corrida": null, "pilates": null,
 "habitos": [],
 "rotina": [],
 "tarefas_feitas": [],
 "novas_tarefas": [{"texto": "...", "data": null}],
 "nao_entendi": []
}

Regras:
- refeicoes: use as chaves da TABELA DE ALIMENTOS sempre que o alimento existir nela; "q" é a quantidade na unidade da tabela (g = gramas, un = unidades/porções como descritas). Converta medidas caseiras (4 colheres de arroz ≈ 100 g, 1 concha de feijão ≈ 100 g, 1 filé de frango ≈ 120 g, 1 bife ≈ 120 g). Quando ele não disser a quantidade, use a porção padrão (def) da tabela.
- Alimento que não está na tabela vai em "outros" com nome curto e estimativa honesta de kcal (k) e proteína em gramas (p) da porção descrita.
- Lanche fora de hora, doce ou bebida calórica: coloque no slot mais próximo do horário (ou "lanche").
- Refeição citada sem nenhum detalhe ("almocei normal"): inclua o slot com "itens": [] e "outros": [] (registra a refeição padrão) e mencione na fala que dá para detalhar.
- passos: número inteiro (8 mil = 8000). remo_min: minutos de remo leve ou caminhada extra em casa. agua_copos: TOTAL do dia em copos de 250 ml (2 litros = 8).
- treino_feito: true se ele disse que fez o treino de musculação do dia. ioga/corrida/pilates: true só se fez.
- habitos: use só estas chaves, quando ele disser que fez: creatina (tomou creatina), caminhada (movimento depois de comer), jantar16 (decidiu o jantar até as 16h).
- rotina: ids da LISTA DO DIA (itens de rotina) que ele disse ter feito, por exemplo vitaminas ou Duolingo. Use exatamente o id.
- tarefas_feitas: números das TAREFAS EM ABERTO que ele disse ter concluído. Só quando for claramente a mesma tarefa.
- novas_tarefas: coisas que ele disse que precisa fazer depois (data em AAAA-MM-DD quando ele disser o dia; "amanhã" = dia seguinte ao DIA DO RELATO).
- Campos sem informação ficam null ou lista vazia."""


def _foods_info(vault):
    """{chave: (nome, unidade, rótulo da unidade, porção padrão, kcal, prot)} lidos da tabela FOODS do treino.html."""
    p = os.path.join(vault, 'App', 'static', 'treino.html')
    try:
        txt = open(p, encoding='utf-8').read()
    except OSError:
        return {}
    out = {}
    for k, n, u, lb, df, kc, pr in re.findall(
            r"(\w+):\{n:'([^']*)',u:'(g|un)',(?:lb:'([^']*)',)?def:([\d.]+),k:([\d.]+),p:([\d.]+)", txt):
        if k not in out:
            out[k] = (n, u, lb, float(df), float(kc), float(pr))
    return out


def _dia_atual(vault, dia):
    p = os.path.join(vault, '20_Treino', 'dias', dia + '.json')
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _resumo_dia(d, foods):
    linhas = []
    for s, nome in SLOTS.items():
        v = (d.get('meals') or {}).get(s)
        if v is True:
            linhas.append('%s: refeição padrão marcada' % nome)
        elif isinstance(v, dict) and v.get('items'):
            linhas.append('%s: %s' % (nome, ', '.join('%s %s' % (foods.get(i.get('f'), (i.get('f'),))[0], i.get('q')) for i in v['items'])))
    for c, nome in (('steps', 'passos'), ('mov', 'remo leve (min)'), ('water', 'água (copos)'), ('sleep', 'sono (h)'), ('weight', 'peso')):
        if d.get(c):
            linhas.append('%s: %s' % (nome, d[c]))
    w = d.get('workout') or {}
    feitos = [k for k in ('done', 'yoga', 'corrida', 'pilates') if w.get(k)]
    if feitos:
        linhas.append('treino: ' + ', '.join(feitos))
    return '\n'.join(linhas) or '(nada registrado ainda)'


def _json_da_resposta(texto):
    t = texto.strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t)
    i, j = t.find('{'), t.rfind('}')
    if i < 0 or j < i:
        raise ValueError('a Vega não devolveu um plano legível; tente de novo')
    return json.loads(t[i:j + 1])


def _num(v, lo, hi, inteiro=False):
    try:
        x = float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        return None
    if not lo <= x <= hi:
        return None
    return int(round(x)) if inteiro else round(x, 1)


def _fmt_q(q, u, lb):
    q = int(q) if float(q).is_integer() else q
    if u != 'g' and q == 1 and lb and lb.endswith('s') and not lb.endswith('ss'):
        lb = lb[:-1]
    return '%s g' % q if u == 'g' else '%s %s' % (q, lb or 'un')


def entender(vault, texto, dia, lista, meta_prot=None):
    """Lê o relato e devolve {fala, acoes:[{id, tipo, rotulo, dados, marcado}], nao_entendi}. Não grava nada."""
    texto = re.sub(r'\s+', ' ', str(texto or '')).strip()
    if len(texto) < 3:
        raise ValueError('conte o seu dia primeiro')
    if len(texto) > 6000:
        texto = texto[:6000]
    if not DATA.match(dia) or dia > date.today().isoformat():
        raise ValueError('dia inválido')
    chave = concierge._chave()
    if not chave:
        raise ValueError('a Vega está sem a chave da API')
    u = concierge._uso()
    if u['usd'] >= u.get('teto', concierge.TETO_PADRAO):
        raise ValueError('teto do mês da Vega atingido')
    foods = _foods_info(vault)
    d = _dia_atual(vault, dia)
    rot = [x for x in lista if x.get('tipo') == 'rotina' and not str(x.get('id', '')).startswith('agua-')]
    tar = [x for x in lista if x.get('tipo') == 'tarefa' and not x.get('feito')]
    tab = '\n'.join('%s | %s | %s%s | porção padrão %s | %g kcal e %g g prot por %s' % (
        k, n, u_, ' (' + lb + ')' if lb else '', df, kc, pr, '100 g' if u_ == 'g' else 'unidade')
        for k, (n, u_, lb, df, kc, pr) in foods.items())
    ctx = ('DIA DO RELATO: %s (%s)\nMETA DE PROTEÍNA: %s\n\nTABELA DE ALIMENTOS (chave | nome | unidade | ...):\n%s\n\n'
           'LISTA DO DIA (rotina):\n%s\n\nTAREFAS EM ABERTO:\n%s\n\nJÁ REGISTRADO HOJE:\n%s') % (
        dia, ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'][date.fromisoformat(dia).weekday()],
        ('%s g' % meta_prot) if meta_prot else 'não informada', tab,
        '\n'.join('- id=%s · %s%s' % (x['id'], x.get('texto', ''), ' (já feito)' if x.get('feito') else '') for x in rot) or '(vazia)',
        '\n'.join('%d. %s' % (i + 1, _titulo_tarefa(x)) for i, x in enumerate(tar)) or '(nenhuma)',
        _resumo_dia(d, foods))
    corpo = {'model': concierge.MODELO, 'max_tokens': 2500, 'system': PROMPT,
             'messages': [{'role': 'user', 'content': ctx + '\n\nRELATO DO MARCIO:\n' + texto}]}
    try:
        r = concierge._post(corpo, chave)
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        raise ValueError('a Vega não conseguiu ler agora (%s); tente de novo' % str(e)[:160])
    us = r.get('usage') or {}
    pi, po = concierge.PRECO.get(concierge.MODELO, (2.0, 10.0))
    u = concierge._uso()
    u['usd'] = u.get('usd', 0) + (us.get('input_tokens', 0) * pi + us.get('output_tokens', 0) * po) / 1e6
    concierge._gravar_uso(u)
    resp = ''.join(b.get('text', '') for b in r.get('content') or [] if b.get('type') == 'text')
    plano = _json_da_resposta(resp)
    return _acoes(plano, foods, d, rot, tar, dia)


def _titulo_tarefa(t):
    tx = t.get('texto') or t.get('titulo') or t.get('linha_txt') or ''
    tx = re.sub(r'^\s*- \[.\]\s*', '', tx)
    return re.sub(r'\s*(📅|⏰|➕|✅|🔁)\s*\S+', '', tx).strip()


def _acoes(plano, foods, d, rot, tar, dia):
    acoes, duvidas = [], []

    def add(tipo, rotulo, dados, marcado=True):
        acoes.append({'id': 'a%d' % (len(acoes) + 1), 'tipo': tipo, 'rotulo': rotulo, 'dados': dados, 'marcado': marcado})

    for r in plano.get('refeicoes') or []:
        s = r.get('slot')
        if s not in SLOTS:
            continue
        itens, desc, kc, pr = [], [], 0.0, 0.0
        for i in r.get('itens') or []:
            f = i.get('f')
            if f not in foods:
                continue
            n, u_, lb, df, fk, fp = foods[f]
            q = _num(i.get('q'), 0.1, 2000) or df
            itens.append({'f': f, 'q': q})
            m = q / 100.0 if u_ == 'g' else q
            kc += fk * m; pr += fp * m
            desc.append('%s %s' % (n.split(' (')[0].lower(), _fmt_q(q, u_, lb)))
        outros = []
        for o in r.get('outros') or []:
            n = re.sub(r'\s+', ' ', str(o.get('n') or '')).strip()[:60]
            k_, p_ = _num(o.get('k'), 0, 3000) or 0, _num(o.get('p'), 0, 200) or 0
            if n:
                outros.append({'n': n, 'k': k_, 'p': p_})
                kc += k_; pr += p_
                desc.append('%s (estimado)' % n.lower())
        atual = (d.get('meals') or {}).get(s)
        if not itens and not outros and r.get('itens'):
            duvidas.append('%s: não reconheci %s' % (SLOTS[s], ', '.join(str(i.get('f')) for i in r['itens'])))
            continue
        if not itens and not outros:
            if atual:
                continue
            dk, dp = treino.REFEICAO_PADRAO.get(s, (0, 0))
            add('refeicao', '%s: refeição padrão (≈ %d kcal · %d g prot) — dá para detalhar depois' % (SLOTS[s], dk, dp),
                {'slot': s, 'itens': [], 'outros': []})
            continue
        ja = ''
        if isinstance(atual, dict) and atual.get('items'):
            ja = ' · soma ao que já estava'
        elif atual is True:
            ja = ' · troca a refeição padrão'
        add('refeicao', '%s: %s (≈ %d kcal · %d g prot)%s' % (SLOTS[s], ', '.join(desc), kc, pr, ja),
            {'slot': s, 'itens': itens, 'outros': outros})

    def campo(chave, tipo, lo, hi, inteiro, rot_fn, atual_k):
        v = _num(plano.get(chave), lo, hi, inteiro)
        if v is None:
            return
        antes = d.get(atual_k)
        extra = ' (antes %s)' % _br(antes) if antes not in (None, '', 0) and antes != v else ''
        add(tipo, rot_fn(v) + extra, {'v': v})

    campo('passos', 'passos', 1, 150000, True, lambda v: 'Passos: %s' % _br(v), 'steps')
    campo('remo_min', 'remo', 1, 300, True, lambda v: 'Remo leve: %d min' % v, 'mov')
    campo('agua_copos', 'agua', 1, 20, True, lambda v: 'Água: %d copos (%s L)' % (v, _br(v * .25)), 'water')
    campo('sono_h', 'sono', 1, 16, False, lambda v: 'Sono: %s h' % _br(v), 'sleep')
    campo('peso_kg', 'peso', 30, 250, False, lambda v: 'Peso: %s kg' % _br(v), 'weight')
    campo('cintura_cm', 'cintura', 40, 200, False, lambda v: 'Cintura: %s cm' % _br(v), 'waist')
    w = d.get('workout') or {}
    for k, wk, nome in (('treino_feito', 'done', 'Treino do dia feito'), ('ioga', 'yoga', 'Ioga feita'),
                        ('corrida', 'corrida', 'Corrida feita'), ('pilates', 'pilates', 'Pilates feito')):
        if plano.get(k) is True and not w.get(wk):
            add('treino', nome, {'k': wk})
    hb = d.get('habits') or {}
    for h in plano.get('habitos') or []:
        if h in HABITOS and not hb.get(h):
            add('habito', HABITOS[h], {'h': h})
    ids = {x['id']: x for x in rot}
    for i in plano.get('rotina') or []:
        x = ids.get(str(i))
        if x and not x.get('feito'):
            lg = x.get('liga') or ''
            wk = {'treino': 'done', 'ioga': 'yoga', 'pilates': 'pilates', 'corrida': 'corrida'}.get(lg)
            if wk:      # rotina ligada ao Treino: grava no Treino (a lista marca sozinha e o desfazer cobre)
                if not w.get(wk) and not any(a['tipo'] == 'treino' and a['dados']['k'] == wk for a in acoes):
                    add('treino', x.get('texto', ''), {'k': wk})
                continue
            if lg:
                continue
            add('rotina', 'Rotina: ' + x.get('texto', ''), {'id': x['id']})
    for n in plano.get('tarefas_feitas') or []:
        try:
            t = tar[int(n) - 1]
        except (ValueError, IndexError, TypeError):
            continue
        add('tarefa', 'Concluir: ' + _titulo_tarefa(t), {'arquivo': t['arquivo'], 'linha': t['linha'], 'linha_txt': t['linha_txt']})
    for t in plano.get('novas_tarefas') or []:
        tx = re.sub(r'\s+', ' ', str((t or {}).get('texto') or '')).strip()[:200]
        if not tx:
            continue
        dt = str((t or {}).get('data') or '')
        dt = dt if DATA.match(dt) else ''
        add('nova_tarefa', 'Nova tarefa: %s%s' % (tx, ' · ' + _data_br(dt) if dt else ''), {'texto': tx, 'data': dt})
    return {'fala': str(plano.get('fala') or '').strip()[:600], 'acoes': acoes, 'dia': dia,
            'nao_entendi': ([str(x)[:160] for x in (plano.get('nao_entendi') or [])] + duvidas)[:6]}


def _br(v):
    if isinstance(v, float) and not v.is_integer():
        return ('%.2f' % v).rstrip('0').rstrip('.').replace('.', ',')
    v = int(v)
    return '{:,}'.format(v).replace(',', '.') if v >= 1000 else str(v)


def _data_br(iso):
    try:
        x = date.fromisoformat(iso)
    except ValueError:
        return iso
    return '%02d/%02d' % (x.day, x.month)


# --------------------------------------------------------------------------- gravar e desfazer

def _pasta_desfazer(vault):
    p = os.path.join(vault, '00_Sistema', 'diario_desfazer')
    os.makedirs(p, exist_ok=True)
    return p


def _hash(p):
    try:
        with open(p, 'rb') as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return None


def _ler_txt(p):
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def aplicar(vault, corpo, alternar, capturar_linha):
    """Grava as ações confirmadas. alternar(arquivo, linha, texto) e capturar_linha(texto) vêm do servidor."""
    dia = str(corpo.get('dia') or '')
    if not DATA.match(dia) or dia > date.today().isoformat():
        raise ValueError('dia inválido')
    acoes = [a for a in (corpo.get('acoes') or []) if isinstance(a, dict)][:60]
    if not acoes:
        raise ValueError('nada marcado para registrar')
    foods = _foods_info(vault)
    desf = {'dia': dia, 'quando': datetime.now().isoformat(timespec='seconds'), 'campos': {}, 'arquivos': {}, 'rotulos': []}
    tarefas_md = os.path.join(vault, '10_Tarefas')

    # arquivos de texto que podem mudar: guardamos o antes (inteiro) para o desfazer
    def guarda(p):
        if p not in desf['arquivos']:
            desf['arquivos'][p] = {'antes': _ler_txt(p)}

    feitos_p = rotina._arq_feitos(vault, dia)
    do_treino = [a for a in acoes if a.get('tipo') in ('refeicao', 'passos', 'remo', 'agua', 'sono', 'peso', 'cintura', 'treino', 'habito')]
    if do_treino:
        def muda(d):
            antes = copy.deepcopy(d)
            for a in do_treino:
                t, x = a['tipo'], a.get('dados') or {}
                if t == 'refeicao':
                    s = x.get('slot')
                    if s not in SLOTS:
                        continue
                    d.setdefault('meals', {})
                    itens = [{'f': i['f'], 'q': float(i['q'])} for i in x.get('itens') or [] if i.get('f') in foods and _num(i.get('q'), 0.1, 2000)]
                    outros = x.get('outros') or []
                    if not itens and not outros:
                        if not d['meals'].get(s):
                            d['meals'][s] = True
                    elif itens:
                        r = d['meals'].get(s)
                        if not isinstance(r, dict):
                            r = {'c': 1, 'items': []}
                        r.setdefault('items', [])
                        tem = {i.get('f') for i in r['items']}
                        r['items'] += [i for i in itens if i['f'] not in tem]
                        d['meals'][s] = r
                    elif d['meals'].get(s) is True:
                        d['meals'][s] = {'c': 1, 'items': []}      # só "outros": tira a padrão para não contar duas vezes
                    elif not d['meals'].get(s):
                        d['meals'][s] = {'c': 1, 'items': []}
                    ex = d.setdefault('extras', [])
                    nomes = {e.get('n') for e in ex}
                    for o in outros:
                        n = '%s · %s (Vega)' % (SLOTS[s], str(o.get('n') or '')[:60])
                        if n not in nomes:
                            ex.append({'n': n, 'k': _num(o.get('k'), 0, 3000) or 0, 'p': _num(o.get('p'), 0, 200) or 0, 't': None})
                elif t in ('passos', 'remo', 'agua', 'sono', 'peso', 'cintura'):
                    k, lo, hi, inteiro = {'passos': ('steps', 1, 150000, True), 'remo': ('mov', 1, 300, True), 'agua': ('water', 1, 20, True),
                                          'sono': ('sleep', 1, 16, False), 'peso': ('weight', 30, 250, False),
                                          'cintura': ('waist', 40, 200, False)}[t]
                    v = _num(x.get('v'), lo, hi, inteiro)
                    if v is not None:
                        d[k] = v
                elif t == 'treino' and x.get('k') in ('done', 'yoga', 'corrida', 'pilates'):
                    w = d.setdefault('workout', {'letter': None, 'sets': {}, 'done': False, 'warm': False, 'remo': False})
                    w[x['k']] = True
                    if x['k'] == 'yoga':
                        w['rec'] = 'ioga'
                elif t == 'habito' and x.get('h') in HABITOS:
                    d.setdefault('habits', {})[x['h']] = True
                desf['rotulos'].append(a.get('rotulo') or t)
            for k in set(antes) | set(d):
                if k != 'updated' and antes.get(k) != d.get(k):
                    desf['campos'][k] = antes.get(k)
        rotina._treino(vault, dia, muda)

    rot = [a for a in acoes if a.get('tipo') == 'rotina']
    if rot:
        guarda(feitos_p)
        for a in rot:
            iid = str((a.get('dados') or {}).get('id') or '')
            try:
                rotina.marcar(vault, {'dia': dia, 'id': iid, 'feito': True})
                desf['rotulos'].append(a.get('rotulo') or iid)
            except ValueError:
                pass
    erros = []
    for a in acoes:
        x = a.get('dados') or {}
        if a.get('tipo') == 'tarefa':
            p = os.path.normpath(os.path.join(vault, str(x.get('arquivo') or '')))
            if not p.startswith(tarefas_md):
                continue
            guarda(p)
            try:
                alternar(x['arquivo'], int(x['linha']), x['linha_txt'])
                desf['rotulos'].append(a.get('rotulo'))
            except (ValueError, KeyError) as e:
                erros.append('%s: %s' % (a.get('rotulo'), e))
        elif a.get('tipo') == 'nova_tarefa':
            tx = re.sub(r'\s+', ' ', str(x.get('texto') or '')).strip()[:200]
            if not tx:
                continue
            if DATA.match(str(x.get('data') or '')):
                tx += ' 📅 ' + x['data']
            guarda(os.path.join(tarefas_md, 'Tarefas.md'))
            capturar_linha(tx)
            desf['rotulos'].append(a.get('rotulo'))
    for p, v in desf['arquivos'].items():
        v['depois'] = _hash(p)
    did = datetime.now().strftime('%Y%m%d-%H%M%S')
    with open(os.path.join(_pasta_desfazer(vault), did + '.json'), 'w', encoding='utf-8') as f:
        json.dump(desf, f, ensure_ascii=False)
    _log(vault, dia, desf['rotulos'], corpo.get('texto'))
    return {'ok': True, 'desfazer': did, 'gravados': len(desf['rotulos']), 'erros': erros}


def _log(vault, dia, rotulos, texto):
    """Diário legível no cofre: 20_Treino/diario/AAAA-MM.md (o relato e o que foi registrado)."""
    p = os.path.join(vault, '20_Treino', 'diario', dia[:7] + '.md')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    novo = not os.path.exists(p)
    with open(p, 'a', encoding='utf-8') as f:
        if novo:
            f.write('# Diário falado — %s\n\nO que você contou para a Vega e o que ela registrou.\n' % dia[:7])
        f.write('\n## %s · %s\n' % (dia, datetime.now().strftime('%H:%M')))
        if texto:
            f.write('> ' + re.sub(r'\s+', ' ', str(texto)).strip()[:4000] + '\n\n')
        for r in rotulos:
            f.write('- ' + str(r) + '\n')


def desfazer(vault, did):
    if not re.match(r'^\d{8}-\d{6}$', str(did or '')):
        raise ValueError('desfazer inválido')
    p = os.path.join(_pasta_desfazer(vault), did + '.json')
    try:
        with open(p, encoding='utf-8') as f:
            desf = json.load(f)
    except (OSError, ValueError):
        raise ValueError('não achei esse registro para desfazer')
    if desf.get('desfeito'):
        raise ValueError('isso já foi desfeito')
    avisos = []
    if desf.get('campos'):
        def volta(d):
            for k, v in desf['campos'].items():
                d[k] = v
        rotina._treino(vault, desf['dia'], volta)
    for arq, v in (desf.get('arquivos') or {}).items():
        if _hash(arq) != v.get('depois'):
            avisos.append('%s mudou depois; desfaça essa parte à mão' % os.path.basename(arq))
            continue
        if v.get('antes') is None:
            try:
                os.remove(arq)
            except OSError:
                pass
        else:
            with open(arq, 'w', encoding='utf-8') as f:
                f.write(v['antes'])
    desf['desfeito'] = datetime.now().isoformat(timespec='seconds')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(desf, f, ensure_ascii=False)
    return {'ok': True, 'avisos': avisos}


# --------------------------------------------------------------------------- microfone: Google Speech-to-Text

def _chave_google():
    try:
        r = subprocess.run(['security', 'find-generic-password', '-s', 'orbitus-google-tts', '-a', 'api', '-w'],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


_ULT = {'msg': ''}


def _stt(pcm, chave, modelo=True):
    cfg = {'encoding': 'LINEAR16', 'sampleRateHertz': 16000, 'languageCode': 'pt-BR', 'enableAutomaticPunctuation': True}
    if modelo:
        cfg['model'] = 'latest_long'
    corpo = json.dumps({'config': cfg, 'audio': {'content': base64.b64encode(pcm).decode()}}).encode()
    url = 'https://speech.googleapis.com/v1/speech:recognize?key=' + chave
    req = urllib.request.Request(url, data=corpo, method='POST', headers={'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode('utf-8'))
        except Exception:
            j = {}
        msg = (j.get('error') or {}).get('message', '')
        if e.code == 400 and modelo and 'model' in msg.lower():
            return _stt(pcm, chave, False)
        if 'are blocked' in msg:
            raise RuntimeError('STT_BLOQUEADA')
        if e.code == 403 or 'SERVICE_DISABLED' in json.dumps(j) or 'has not been used' in msg or 'disabled' in msg.lower():
            _ULT['msg'] = msg[:300]; raise RuntimeError('STT_DESLIGADO')
        raise RuntimeError('o Google respondeu %s%s' % (e.code, ': ' + msg[:200] if msg else ''))
    except urllib.error.URLError:
        r = subprocess.run(['/usr/bin/curl', '-sS', '--max-time', '90', url, '-H', 'content-type: application/json',
                            '--data-binary', '@-'], input=corpo, capture_output=True, timeout=100)
        j = json.loads(r.stdout.decode('utf-8') or '{}')
        if j.get('error'):
            msg = j['error'].get('message', '')
            if 'are blocked' in msg:
                raise RuntimeError('STT_BLOQUEADA')
            if 'SERVICE_DISABLED' in json.dumps(j) or 'has not been used' in msg or 'disabled' in msg.lower():
                _ULT['msg'] = msg[:300]; raise RuntimeError('STT_DESLIGADO')
            raise RuntimeError('o Google respondeu: ' + msg[:200])
        return j


def transcrever(corpo):
    """corpo: {'pcm': base64 de PCM 16 bits, 16 kHz, mono} com até ~58 s. Devolve {'texto'}."""
    chave = _chave_google()
    if not chave:
        raise ValueError('falta a chave do Google no Chaves (orbitus-google-tts)')
    try:
        pcm = base64.b64decode(str(corpo.get('pcm') or ''), validate=False)
    except (ValueError, TypeError):
        raise ValueError('áudio inválido')
    if pcm[:4] == b'RIFF':
        pcm = pcm[44:]
    if len(pcm) < 3200:
        return {'texto': ''}
    if len(pcm) > 16000 * 2 * 58:
        raise ValueError('trecho de áudio longo demais')
    try:
        j = _stt(pcm, chave)
    except RuntimeError as e:
        if str(e) == 'STT_DESLIGADO':
            raise ValueError('O microfone novo precisa da API "Cloud Speech-to-Text" ligada no mesmo projeto do Google da voz. '
                             'Abra console.cloud.google.com, APIs e serviços, Biblioteca, procure "Cloud Speech-to-Text API" e clique em Ativar. '
                             'Enquanto isso, use o ditado do teclado no campo de texto. (Google: %s)' % _ULT['msg'][:160])
        if str(e) == 'STT_BLOQUEADA':
            raise ValueError('A chave do Google da Vega só libera a voz (Text-to-Speech), por isso o áudio não foi transcrito. '
                             'No console.cloud.google.com: APIs e serviços › Credenciais › abra a chave da Vega › Restrições de API › '
                             'marque também "Cloud Speech-to-Text API" › Salvar. Leva uns minutos para valer.')
        raise ValueError(str(e))
    partes = [((r.get('alternatives') or [{}])[0].get('transcript') or '').strip() for r in j.get('results') or []]
    return {'texto': ' '.join(p for p in partes if p)}
