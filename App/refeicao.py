# -*- coding: utf-8 -*-
"""Orbitus — estimar uma refeição descrita em texto livre (aba Treino › Comida, 13/11/2026).

Antes, a estimativa era só local (sinônimos da tabela): "não reconheci" para quase tudo que fugia da lista.
Agora o servidor pede ao Claude: usa a tabela FOODS quando o alimento existe; o resto vem com kcal e proteína estimadas.
"""
import json, re

import concierge
import diario

PROMPT = """Você estima refeições descritas por um adulto brasileiro. Quebre em itens.
Para cada item, use um id da TABELA quando o alimento for equivalente e informe q na unidade da tabela (g = gramas; un = a unidade descrita).
Converta medidas caseiras (4 colheres de arroz ≈ 100 g; 1 concha de feijão ≈ 100 g; 1 filé ≈ 120 g; 1 bife ≈ 120 g).
Sem quantidade informada, use a porção padrão (def) da tabela ou uma porção caseira típica.
Se o alimento não estiver na tabela, use "food": null e estime kcal e proteína (g) da porção descrita, com honestidade.
Bebidas sem caloria (água, café sem açúcar, chá) não entram.
Responda SOMENTE com JSON: {"itens":[{"nome":"texto curto","food":"id ou null","q":número,"kcal":número,"proteina_g":número}]}"""


def estimar(vault, corpo):
    txt = re.sub(r'\s+', ' ', str(corpo.get('texto') or '')).strip()[:1500]
    if len(txt) < 2:
        raise ValueError('descreva a refeição')
    chave = concierge._chave()
    if not chave:
        raise ValueError('sem a chave da API')
    u = concierge._uso()
    if u.get('usd', 0) >= u.get('teto', concierge.TETO_PADRAO):
        raise ValueError('teto do mês de uso da IA atingido')
    foods = diario._foods_info(vault)
    tab = '\n'.join('%s | %s | %s%s | def %s | %g kcal e %g g prot por %s' % (
        k, n, u_, ' (' + lb + ')' if lb else '', df, kc, pr, '100 g' if u_ == 'g' else 'unidade')
        for k, (n, u_, lb, df, kc, pr) in foods.items())
    corpo_api = {'model': concierge.MODELO, 'max_tokens': 900, 'system': PROMPT,
                 'messages': [{'role': 'user', 'content': 'TABELA (id | nome | unidade | ...):\n' + tab + '\n\nREFEIÇÃO: ' + txt}]}
    try:
        r = concierge._post(corpo_api, chave)
    except Exception as e:
        raise ValueError('a estimativa falhou agora (%s)' % str(e)[:120])
    us = r.get('usage') or {}
    pi, po = concierge.PRECO.get(concierge.MODELO, (2.0, 10.0))
    u = concierge._uso()
    u['usd'] = u.get('usd', 0) + (us.get('input_tokens', 0) * pi + us.get('output_tokens', 0) * po) / 1e6
    concierge._gravar_uso(u)
    resp = ''.join(b.get('text', '') for b in r.get('content') or [] if b.get('type') == 'text')
    j = diario._json_da_resposta(resp)
    itens = []
    for it in (j.get('itens') or [])[:20]:
        f = it.get('food')
        f = f if f in foods else None
        try:
            q = float(it.get('q') or 0)
        except (TypeError, ValueError):
            q = 0
        itens.append({'nome': str(it.get('nome') or 'Item')[:60], 'food': f, 'q': q,
                      'kcal': diario._num(it.get('kcal'), 0, 3000) or 0, 'proteina_g': diario._num(it.get('proteina_g'), 0, 200) or 0})
    return {'itens': itens}
