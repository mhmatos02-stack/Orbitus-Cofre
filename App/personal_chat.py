# -*- coding: utf-8 -*-
"""Orbitus — conversa ao vivo com o Personal (Brasa) durante o treino.

A aba Treino manda a pergunta e o retrato da sessão (exercícios, séries feitas, cargas); o servidor junta o perfil do
agente (Mesa da Saúde/agentes/personal.md), o local, o registro do dia e o último parecer do personal.
A conversa do dia fica em 20_Treino/Mesa da Saúde/conversas/AAAA-MM-DD.jsonl, e o parecer da noite pode lê-la.
"""
import json, os, re
from datetime import date, datetime

import concierge

DATA = re.compile(r'^\d{4}-\d{2}-\d{2}$')

REGRAS = """
## Agora: conversa ao vivo durante o treino
O Marcio está treinando neste momento e escreve entre as séries, no celular. Responda como um personal ao lado dele:
- No máximo 4 frases curtas, em português, direto ao ponto. Sem títulos, sem listas longas, sem markdown pesado.
- Use os dados da SESSÃO DE HOJE (exercício, carga, repetições, descanso) para responder de forma concreta: diga a carga, as repetições ou a troca de exercício.
- Ajuste de carga em passos pequenos (1 a 2 kg por halter) e dentro da progressão dupla.
- Troca de exercício: prefira um da mesma família que dê para fazer com o equipamento do local.
- Dor aguda, pontada, estalo com dor, formigamento, tontura, falta de ar fora do normal ou dor no peito: mande parar o exercício na hora; se não passar, procurar atendimento médico. Não diagnostique.
- Se a pergunta não for de treino, responda curto e devolva o foco para a série.
- Não invente dados que não estão no contexto. Se faltar algo para responder bem, faça UMA pergunta curta."""


def _pasta(vault):
    return os.path.join(vault, '20_Treino', 'Mesa da Saúde')


def _arq(vault, dia):
    p = os.path.join(_pasta(vault), 'conversas')
    os.makedirs(p, exist_ok=True)
    return os.path.join(p, dia + '.jsonl')


def historico(vault, dia):
    if not DATA.match(str(dia or '')):
        raise ValueError('dia inválido')
    out = []
    try:
        with open(_arq(vault, dia), encoding='utf-8') as f:
            for l in f:
                try:
                    out.append(json.loads(l))
                except ValueError:
                    pass
    except OSError:
        pass
    return {'mensagens': out[-40:]}


def _ler(p):
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def _perfil(vault):
    t = _ler(os.path.join(_pasta(vault), 'agentes', 'personal.md'))
    return t.split('---', 2)[2].strip() if t.startswith('---') and t.count('---') >= 2 else t


def _contexto_servidor(vault, dia):
    partes = []
    loc = _ler(os.path.join(vault, '20_Treino', 'locais.json'))
    if loc:
        partes.append('LOCAIS (locais.json): ' + loc[:600])
    try:
        d = json.loads(_ler(os.path.join(vault, '20_Treino', 'dias', dia + '.json')) or '{}')
    except ValueError:
        d = {}
    reg = {k: d.get(k) for k in ('weight', 'waist', 'steps', 'sleep', 'water', 'mov') if d.get(k) not in (None, '')}
    if reg:
        partes.append('REGISTRO DO DIA: ' + json.dumps(reg, ensure_ascii=False))
    pd = os.path.join(_pasta(vault), 'pareceres')
    try:
        ult = sorted(n for n in os.listdir(pd) if n.endswith('.json'))[-1]
        par = json.loads(_ler(os.path.join(pd, ult)) or '{}')
        pe = (par.get('agentes') or {}).get('personal')
        if pe:
            partes.append('SEU ÚLTIMO PARECER (%s): %s' % (ult[:10], json.dumps(pe, ensure_ascii=False)[:1500]))
    except (OSError, IndexError, ValueError):
        pass
    return '\n'.join(partes)


def perguntar(vault, corpo):
    dia = str(corpo.get('dia') or date.today().isoformat())[:10]
    if not DATA.match(dia):
        raise ValueError('dia inválido')
    texto = re.sub(r'\s+', ' ', str(corpo.get('texto') or '')).strip()[:800]
    if not texto:
        raise ValueError('escreva a pergunta')
    sessao = str(corpo.get('sessao') or '')[:4000]
    chave = concierge._chave()
    if not chave:
        raise ValueError('o Personal está sem a chave da API')
    u = concierge._uso()
    if u.get('usd', 0) >= u.get('teto', concierge.TETO_PADRAO):
        raise ValueError('teto do mês de uso da IA atingido')
    hist = historico(vault, dia)['mensagens'][-12:]
    msgs = []
    for m in hist:
        msgs.append({'role': 'user', 'content': m['pergunta']})
        msgs.append({'role': 'assistant', 'content': m['resposta']})
    ctx = 'HOJE: %s · agora %s\n%s\n\nSESSÃO DE HOJE (da aba Treino):\n%s' % (
        dia, datetime.now().strftime('%H:%M'), _contexto_servidor(vault, dia), sessao or '(não veio)')
    msgs.append({'role': 'user', 'content': ctx + '\n\nPERGUNTA: ' + texto})
    corpo_api = {'model': concierge.MODELO, 'max_tokens': 700, 'system': _perfil(vault) + '\n' + REGRAS, 'messages': msgs}
    try:
        r = concierge._post(corpo_api, chave)
    except Exception as e:
        raise ValueError('o Personal não respondeu agora (%s); tente de novo' % str(e)[:140])
    us = r.get('usage') or {}
    pi, po = concierge.PRECO.get(concierge.MODELO, (2.0, 10.0))
    u = concierge._uso()
    u['usd'] = u.get('usd', 0) + (us.get('input_tokens', 0) * pi + us.get('output_tokens', 0) * po) / 1e6
    concierge._gravar_uso(u)
    resp = ''.join(b.get('text', '') for b in r.get('content') or [] if b.get('type') == 'text').strip()
    if not resp:
        raise ValueError('o Personal ficou sem resposta; tente de novo')
    item = {'em': datetime.now().isoformat(timespec='seconds'), 'pergunta': texto, 'resposta': resp}
    with open(_arq(vault, dia), 'a', encoding='utf-8') as f:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')
    return item
