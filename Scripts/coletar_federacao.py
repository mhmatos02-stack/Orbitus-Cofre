#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orbitus — coleta o _orbitus/ de cada sistema federado e gera 01_Federacao/<id>.md.

Só biblioteca padrão. Roda no Mac (launchd) e no shell das tarefas agendadas.
Caminhos relativos: o Orbitus e os sistemas são irmãos dentro de ~/System.
"""
import json, os, re, sys
from datetime import date, datetime

ORB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAE = os.path.dirname(ORB)
SAIDA = os.path.join(ORB, '01_Federacao')
HOJE = date.today()
COR = {'verde': '🟢', 'amarelo': '🟡', 'vermelho': '🔴'}
NIVEL = {'🟢': 0, '🟡': 1, '🔴': 2, '⚪': 3}


def ler(p):
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def campo(txt, nome):
    m = re.search(r'\*\*' + nome + r'[^*]*:\*\*\s*(.+)', txt or '')
    return m.group(1).strip() if m else ''


def limpa(s, n=220):
    s = re.sub(r'\*\*|`', '', s).strip()
    return s if len(s) <= n else s[:n].rsplit(' ', 1)[0] + '…'


def data_em(s):
    m = re.search(r'(\d{4}-\d{2}-\d{2})', s or '')
    return date.fromisoformat(m.group(1)) if m else None


def pior(a, b):
    return a if NIVEL[a] >= NIVEL[b] else b


def esperando_mesa(base):
    """2026-10-30: o "Esperando de você" do Wealth é calculado na hora a partir da Mesa (arquivos),
    não do texto semanal do CIO. Resposta já enviada pelo Orbitus (respostas.jsonl) conta como feita."""
    mesa = os.path.join(base, '_orbitus', 'mesa')
    if not os.path.isdir(mesa):
        return None
    def col(n):
        try:
            return json.loads(ler(os.path.join(mesa, n + '.json')) or '{}').get('itens', {})
        except ValueError:
            return {}
    resp = set()
    for l in (ler(os.path.join(mesa, 'respostas.jsonl')) or '').splitlines():
        try:
            r = json.loads(l); resp.add((r.get('tipo'), r.get('id')))
        except ValueError:
            pass
    hoje = HOJE.isoformat()
    itens = []
    for k, d in col('decisoes').items():
        if d.get('status') == 'aberta' and ('decisao', k) not in resp:
            itens.append((d.get('prazo') or '9999', 'Decidir na Mesa: ' + (d.get('titulo') or d.get('ref') or k)))
    lanc = [k for k, d in col('lancamentos').items() if d.get('status') == 'aguardando' and ('lancamento', k) not in resp]
    if lanc:
        itens.append(('0000', 'Confirmar %d lançamento(s) na Mesa' % len(lanc)))
    for k, p in col('plano').items():
        if p.get('quem') == 'voce' and p.get('status') != 'feito' and ('plano', k) not in resp \
                and p.get('inicio') and p['inicio'] <= hoje:
            fim = p.get('fim') or p['inicio']
            quando = 'atrasado desde ' + fim[8:10] + '/' + fim[5:7] if fim < hoje else 'até ' + fim[8:10] + '/' + fim[5:7]
            itens.append((fim, p.get('acao', k) + ' (' + quando + ')'))
    itens.sort()
    return [t for _, t in itens]


def coletar(s):
    base = os.path.join(MAE, s['pasta'])
    status = ler(os.path.join(base, '_orbitus', 'STATUS.md'))
    msg = ler(os.path.join(base, '_orbitus', 'MENSAGEM.md'))
    auto = ler(os.path.join(base, '00_System', 'Automation Status.md'))
    r = {'id': s['id'], 'nome': s['nome'], 'icone': s.get('icone', '◉'), 'coletado': HOJE.isoformat()}
    if status is None:
        r.update(saude='⚪', motivo='pasta ou STATUS não encontrado', idade=-1)
        return r
    saude_txt = campo(status, 'Saúde').lower()
    cor = next((v for k, v in COR.items() if saude_txt.startswith(k) or v in saude_txt), '🟡')
    db = data_em(campo(status, 'Data-base'))
    idade = (HOJE - db).days if db else 999
    motivo = ''
    if idade > 15:
        cor, motivo = '🔴', f'parado: sem STATUS há {idade} dias'
    elif idade > 8:
        cor, motivo = pior(cor, '🟡'), f'sem sinal recente ({idade} dias)'
    auto_res = campo(auto, 'Resultado') if auto else ''
    auto_quando = data_em(auto) if auto else None
    if auto_res:
        ac = '🔴' if '🔴' in auto_res else '🟡' if '🟡' in auto_res else '🟢'
        if auto_quando and (HOJE - auto_quando).days > 2:
            ac, auto_res = '🔴', f'health-check parado desde {auto_quando}'
        cor = pior(cor, ac)
    falhas = []
    for linha in (auto or '').splitlines():
        if linha.startswith('| 🔴'):
            partes = [p.strip() for p in linha.strip('|').split('|')]
            if len(partes) >= 3:
                falhas.append(limpa(f'{partes[1]}: {partes[2]}', 140))
    esperando = campo(msg, 'Esperando de você')
    viva = esperando_mesa(base)
    if viva is not None:
        esperando = ' · '.join(viva)
    r.update(saude=cor, motivo=motivo, idade=idade, data_base=db.isoformat() if db else '',
             saude_txt=limpa(campo(status, 'Saúde')), proxima=limpa(campo(status, 'Próxima ação')),
             decisoes=limpa(campo(status, 'Decisões que precisam')), risco=limpa(campo(status, 'Risco')),
             esperando=limpa(esperando, 400), esperando_lista=(viva if viva is not None else ([esperando] if esperando else [])),
             automacao=limpa(auto_res, 120), falhas=falhas[:5])
    return r


def yaml_val(v):
    if isinstance(v, list):
        return '\n' + ''.join(f'  - {json.dumps(x, ensure_ascii=False)}\n' for x in v) if v else ' []\n'
    return ' ' + json.dumps(v, ensure_ascii=False) + '\n'


def main():
    cfg = json.loads(ler(os.path.join(ORB, '00_Sistema', 'sistemas.json')))
    os.makedirs(SAIDA, exist_ok=True)
    out = []
    for s in cfg['sistemas']:
        if not s.get('ativo'):
            continue
        r = coletar(s)
        fm = '---\ntipo: federacao\n' + ''.join(f'{k}:{yaml_val(v)}' for k, v in r.items()) + '---\n'
        corpo = (f"# {r['icone']} {r['nome']}\n\n> Gerado por `coletar_federacao.py` em {HOJE}. Não editar.\n\n"
                 f"**Saúde:** {r['saude']} {r.get('motivo') or r.get('saude_txt', '')}\n\n"
                 f"**Esperando de você:** {r.get('esperando') or '—'}\n\n**Próxima ação:** {r.get('proxima') or '—'}\n")
        with open(os.path.join(SAIDA, s['id'] + '.md'), 'w', encoding='utf-8') as f:
            f.write(fm + corpo)
        out.append(f"{r['saude']} {r['nome']} (STATUS de {r.get('data_base') or '?'})")
    print('\n'.join(out))


if __name__ == '__main__':
    sys.exit(main())
