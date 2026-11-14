# -*- coding: utf-8 -*-
"""Orbitus — Mesa de Decisões (lê o AI Wealth Office, grava só respostas.jsonl).

O estado da Mesa pertence ao AI Wealth Office: <Wealth>/_orbitus/mesa/*.json.
O Orbitus lê esses arquivos e acrescenta as respostas do investidor em respostas.jsonl,
com a mesma trava do Scripts/mesa_arquivos.py do Wealth. A rotina das 20h47 aplica.
"""
import fcntl, glob, json, os, re
from datetime import datetime

COLS = ('decisoes', 'lancamentos', 'atualizacoes', 'plano', 'entregas')
TIPOS = {'decisao': 'decisoes', 'lancamento': 'lancamentos', 'atualizacao': 'atualizacoes', 'plano': 'plano'}

AGENTES = [
    # código, nome, função, grupo
    ('CIO', 'Síntese', 'Pesa os argumentos, escreve a ata e recomenda. Não vota por maioria.', 'cio'),
    ('A1', 'Valor', 'Ações BR abaixo do valor justo, com margem de segurança.', 'esp'),
    ('A2', 'Qualidade', 'Empresas excelentes a preço justo, horizonte de 10 anos.', 'esp'),
    ('J1', 'Trava agora', 'Renda fixa: travar IPCA+ longo com juro real alto.', 'esp'),
    ('J2', 'Pós-fixado', 'Renda fixa: Selic/CDI e flexibilidade; cético com o pico.', 'esp'),
    ('F1', 'Tijolo', 'FIIs de imóveis reais, renda isenta abaixo do valor patrimonial.', 'esp'),
    ('F2', 'Crédito', 'FIIs de papel e Fiagro: qualidade de crédito.', 'esp'),
    ('I1', 'Dolarizar', 'Internacional: tirar parte do patrimônio do Brasil, aos poucos.', 'esp'),
    ('I2', 'Brasil barato', 'Internacional: ativos brasileiros baratos; não dolarizar no fundo.', 'esp'),
    ('R1', 'Gestor de risco', 'Perda máxima, concentração, liquidez e risco de renda.', 'esp'),
    ('R2', 'Comportamental', 'Caça vieses do plano e do investidor.', 'esp'),
    ('P1', 'Tributarista', 'Isenção, prejuízo a compensar e IR de cada destino.', 'esp'),
    ('P2', 'Planejador', 'A carteira a serviço da vida: renda, gasto e meta.', 'esp'),
    ('AD', 'Advogado do Diabo', 'Ataca a proposta vencedora com número e pré-mortem.', 'ad'),
    ('BUF', 'Lente Buffett', 'Princípios publicados: qualidade a preço justo, décadas.', 'lente'),
    ('DAL', 'Lente Dalio', 'Princípios publicados: equilíbrio entre ambientes.', 'lente'),
    ('MRK', 'Lente Marks', 'Princípios publicados: ciclos e segundo nível.', 'lente'),
    ('BAR', 'Lente Barsi', 'Princípios publicados: carteira previdenciária de dividendos.', 'lente'),
    ('BOG', 'Lente Bogle', 'Princípios publicados: custo baixo e simplicidade.', 'lente'),
]


def _ler(p):
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def pasta_wealth(vault):
    mae = os.path.dirname(vault)
    try:
        cfg = json.loads(_ler(os.path.join(vault, '00_Sistema', 'sistemas.json')))
        p = next(s['pasta'] for s in cfg['sistemas'] if s['id'] == 'wealth')
    except Exception:
        p = 'AI Wealth Office'
    return os.path.join(mae, p)


def _respostas(mesa):
    out = []
    for l in (_ler(os.path.join(mesa, 'respostas.jsonl')) or '').splitlines():
        try:
            out.append(json.loads(l))
        except ValueError:
            pass
    return out


def _votos(wealth):
    """Último debate em 07_REPORTS/Mesa: voto, confiança e gatilho de cada agente (rodada mais alta)."""
    pastas = sorted(glob.glob(os.path.join(wealth, '07_REPORTS', 'Mesa', '*')))
    pastas = [p for p in pastas if os.path.isdir(p)]
    if not pastas:
        return None, {}
    ult = pastas[-1]
    rodadas = sorted([d for d in glob.glob(os.path.join(ult, 'r*')) if os.path.isdir(d) and re.search(r'/r\d+$', d)],
                     key=lambda d: int(re.search(r'(\d+)$', d).group(1)))
    votos = {}
    if rodadas:
        for f in glob.glob(os.path.join(rodadas[-1], '*.md')):
            cod = os.path.basename(f)[:-3]
            t = _ler(f) or ''
            m = re.search(r'\*\*Voto:\*\*\s*([^·\n]+?)\s*·\s*\*\*Confiança:\*\*\s*(\d+)', t)
            g = re.search(r'\*\*O que mudaria o meu voto:\*\*\s*(.+)', t)
            if m:
                votos[cod] = {'voto': m.group(1).strip(), 'confianca': int(m.group(2)),
                              'gatilho': (g.group(1).strip()[:280] if g else '')}
    nome = os.path.basename(ult)
    dm = re.match(r'(\d{4}-\d{2}-\d{2})\s+(.*)', nome)
    info = {'pasta': nome, 'data': dm.group(1) if dm else '', 'tema': dm.group(2) if dm else nome}
    return info, votos


def estado(vault):
    wealth = pasta_wealth(vault)
    mesa = os.path.join(wealth, '_orbitus', 'mesa')
    out = {'disponivel': os.path.isdir(mesa)}
    if not out['disponivel']:
        return out
    for c in COLS:
        try:
            itens = json.loads(_ler(os.path.join(mesa, c + '.json')) or '{}').get('itens', {})
        except ValueError:
            itens = {}
        out[c] = [dict(v, id=k) for k, v in itens.items()]
    pend = {}
    for r in _respostas(mesa):
        pend['%s:%s' % (r.get('tipo'), r.get('id'))] = r
    out['respostas'] = pend
    info, votos = _votos(wealth)
    out['ultima_mesa'] = info
    out['agentes'] = [dict(codigo=c, nome=n, funcao=f, grupo=g, **(votos.get(c) or {})) for c, n, f, g in AGENTES]
    return out


def decisoes_abertas(vault):
    e = estado(vault)
    if not e.get('disponivel'):
        return []
    return [d for d in e['decisoes'] if aberta(d)]


def aberta(d):
    """Decisão esperando você: o Wealth usa 'aberta' e, desde 11/11, também 'aguardando' (sem escolha registrada)."""
    return d.get('status') in ('aberta', 'aguardando') and not d.get('escolha')


def responder(vault, corpo):
    tipo, id_ = corpo.get('tipo'), corpo.get('id')
    if tipo not in TIPOS or not isinstance(id_, str):
        raise ValueError('resposta inválida')
    wealth = pasta_wealth(vault)
    mesa = os.path.join(wealth, '_orbitus', 'mesa')
    itens = json.loads(_ler(os.path.join(mesa, TIPOS[tipo] + '.json')) or '{}').get('itens', {})
    doc = itens.get(id_)
    if doc is None:
        raise ValueError('item não existe na Mesa')
    nota = str(corpo.get('nota') or '')[:1000]
    r = {'tipo': tipo, 'id': id_, 'nota': nota, 'em': datetime.now().isoformat(timespec='seconds')}
    if tipo == 'decisao':
        ids = {o.get('id') for o in doc.get('opcoes', [])}
        if corpo.get('escolha') not in ids:
            raise ValueError('opção inválida')
        r['escolha'] = corpo['escolha']
    elif tipo == 'lancamento':
        if corpo.get('acao') not in ('confirmado', 'corrigido', 'descartado'):
            raise ValueError('ação inválida')
        r['acao'] = corpo['acao']
        for k in ('ativo', 'quantidade', 'preco', 'data'):
            v = corpo.get(k)
            if v not in (None, ''):
                if k in ('quantidade', 'preco'):
                    v = float(str(v).replace('.', '').replace(',', '.')) if ',' in str(v) else float(v)
                r[k] = v
    elif tipo == 'plano':
        if doc.get('quem') != 'voce' or corpo.get('acao') not in ('feito', 'desfazer'):
            raise ValueError('passo do plano inválido')
        r['acao'] = corpo['acao']
    else:
        if corpo.get('acao') not in ('aprovado', 'ajuste'):
            raise ValueError('ação inválida')
        r['acao'] = corpo['acao']
    os.makedirs(mesa, exist_ok=True)
    with open(os.path.join(mesa, '.lock'), 'w') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            with open(os.path.join(mesa, 'respostas.jsonl'), 'a', encoding='utf-8') as f:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
    return r
