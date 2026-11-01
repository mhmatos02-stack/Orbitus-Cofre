# -*- coding: utf-8 -*-
"""Orbitus — conversa com o CIO do AI Wealth Office (1:1 sob demanda).

O CIO responde com a própria skill (SKILLS/Chief Investment Officer (CIO).md), o IPS, as restrições, a última ata da
Mesa, o último 1:1, o Decision Journal recente, as pendências da Mesa e a foto atual da carteira.
Somente leitura no Wealth. Duas escritas, ambas previstas no Protocolo de Federação:
  - a conversa fica no cofre do Orbitus: 01_Federacao/Conversas com o CIO/AAAA-MM-DD.md
  - "Levar ao 1:1": acrescenta um despacho em <Wealth>/_orbitus/INBOX.md (o 1:1 de domingo processa e marca).
Nunca executa ordem. Decisão formal continua sendo da Mesa/Decision Journal; o CIO aqui conversa e recomenda.
"""
import fcntl, glob, json, os, re, threading, time
from datetime import date, datetime

TRAVA = threading.Lock()
CONV = {'t': 0, 'msgs': []}

REGRAS = """Você é o CIO do AI Wealth Office do Marcio, numa conversa 1:1 pedida por ele pelo Orbitus (fora do 1:1 de domingo).
Use a sua skill, o IPS, as restrições, a ata da última Mesa, o último 1:1, o Decision Journal e a foto da carteira que estão abaixo.

Como conversar:
- Português do Brasil, direto, como um CIO falando com o dono do patrimônio. Primeiro a resposta, depois o porquê em poucas linhas. Sem tabelas longas; use números concretos quando ajudarem.
- Cite de onde vem cada número (ata de tal data, IPS §x, foto de hoje). Se o dado não estiver aqui, diga que não está e onde buscaria. Não invente preço, data nem decisão.
- Você recomenda; quem decide é o Marcio. Nada que você disser aqui vira decisão formal: decisão de compra, venda ou mudança de regra precisa passar pela Mesa e entrar no Decision Journal. Quando a conversa chegar nisso, diga claramente "isso precisa ir à Mesa" e sugira levar ao 1:1 (o botão "Levar ao 1:1" registra o pedido).
- Respeite a precedência: Constitution > IPS > CIO > Skills. Se o que ele propõe fere o IPS, diga qual regra e o que teria de mudar.
- Você não executa ordens, não acessa corretora e não move dinheiro. Isto é o gestor do sistema dele, não aconselhamento de profissional licenciado.
- Seja honesto e cético, inclusive com o plano que a própria Mesa aprovou, e caçe vieses (pressa, ancoragem, FOMO)."""


def _ler(p, limite=None, cauda=False):
    try:
        with open(p, encoding='utf-8') as f:
            t = f.read()
    except OSError:
        return ''
    if limite and len(t) > limite:
        t = ('…' + t[-limite:]) if cauda else (t[:limite] + '…')
    return t


def _ultimo(padrao):
    fs = sorted(glob.glob(padrao))
    return fs[-1] if fs else ''


def documentos(wealth):
    """Bloco grande e estável (vai em cache na API): skill, IPS, restrições, ata, 1:1, journal."""
    partes = []
    def add(titulo, texto):
        if texto.strip():
            partes.append('=== %s ===\n%s' % (titulo, texto.strip()))
    add('SKILL DO CIO', _ler(os.path.join(wealth, 'SKILLS', 'Chief Investment Officer (CIO).md'), 14000))
    add('INVESTMENT POLICY STATEMENT (IPS)', _ler(os.path.join(wealth, '01_GOVERNANCE', 'Investment Policy Statement.md'), 30000))
    add('RESTRIÇÕES', _ler(os.path.join(wealth, '01_GOVERNANCE', 'Constraints.md'), 3000))
    mesa = _ultimo(os.path.join(wealth, '07_REPORTS', 'Mesa', '*'))
    if mesa:
        add('ÚLTIMA MESA · ' + os.path.basename(mesa) + ' · contexto', _ler(os.path.join(mesa, 'contexto.md'), 6000))
        add('ÚLTIMA MESA · ' + os.path.basename(mesa) + ' · ata (parte final)', _ler(os.path.join(mesa, 'ata.md'), 16000, cauda=True))
    um = _ultimo(os.path.join(wealth, '07_REPORTS', 'CIO', '*1on1 CIO.md'))
    if um:
        add('ÚLTIMO 1:1 · ' + os.path.basename(um), _ler(um, 9000))
    add('DECISION JOURNAL (mais recente)', _ler(os.path.join(wealth, '01_GOVERNANCE', 'Decision Journal.md'), 9000, cauda=True))
    add('RADAR DE OPORTUNIDADES (05_RESEARCH)', _ler(os.path.join(wealth, '05_RESEARCH', 'Radar de Oportunidades.md'), 14000))
    add('TRIAGEM DO RADAR (03_PORTFOLIO/radar_oportunidades.csv, gerada por Scripts/radar_oportunidades.py)',
        _ler(os.path.join(wealth, '03_PORTFOLIO', 'radar_oportunidades.csv'), 8000))
    return '\n\n'.join(partes)


def pendencias(wealth):
    out = {}
    for col in ('decisoes', 'plano', 'lancamentos'):
        try:
            itens = json.loads(_ler(os.path.join(wealth, '_orbitus', 'mesa', col + '.json')) or '{}').get('itens', {})
        except ValueError:
            itens = {}
        vivos = [v for v in itens.values() if v.get('status') in ('aberta', 'pendente', 'aguardando')]
        out[col] = [{k: v.get(k) for k in ('id', 'titulo', 'pergunta', 'acao', 'inicio', 'prazo', 'condicao', 'quem', 'status', 'opcoes') if v.get(k)}
                    for v in vivos][:25]
    return out


def foto(w):
    if not w:
        return {}
    c = {k: w.get(k) for k in ('data_base', 'total', 'caixa', 'reserva', 'renda_mensal_liq', 'meta_renda', 'meta_patrimonio',
                              'modo_preservacao', 'classes', 'bandas', 'alertas', 'decidir', 'isencao', 'proventos_proximos')}
    c['posicoes'] = [{k: a.get(k) for k in ('ticker', 'classe', 'qtd', 'pm', 'preco', 'valor', 'ganho_pct', 'peso', 'tag')}
                     for a in (w.get('acoes') or []) + (w.get('fiis') or []) + (w.get('etfs') or [])] + (w.get('outros') or [])
    c['agenda'] = (w.get('agenda') or [])[:20]
    return c


def preparar(pergunta, wealth, w, modelo, chave):
    pergunta = re.sub(r'\s+', ' ', str(pergunta or '')).strip()[:2000]
    if not pergunta:
        raise ValueError('escreva a pergunta para o CIO')
    if not os.path.isdir(wealth):
        raise ValueError('não achei a pasta do AI Wealth Office')
    with TRAVA:
        if time.time() - CONV['t'] > 3600:
            CONV['msgs'] = []
        hist = CONV['msgs'][-10:]
    agora = datetime.now()
    dinamico = 'Agora: %s.\n\nPENDÊNCIAS DA MESA (JSON):\n%s\n\nFOTO DA CARTEIRA (JSON, do painel do Wealth):\n%s' % (
        agora.strftime('%Y-%m-%d %H:%M'), json.dumps(pendencias(wealth), ensure_ascii=False, default=str),
        json.dumps(foto(w), ensure_ascii=False, separators=(',', ':'), default=str))
    corpo = {'model': modelo, 'max_tokens': 12000,
             'system': [{'type': 'text', 'text': REGRAS},
                        {'type': 'text', 'text': documentos(wealth), 'cache_control': {'type': 'ephemeral'}},
                        {'type': 'text', 'text': dinamico}],
             'messages': hist + [{'role': 'user', 'content': pergunta}],
             'output_config': {'effort': 'medium'}}
    return {'pergunta': pergunta, 'corpo': corpo, 'chave': chave}


def finalizar(prep, texto, vault):
    with TRAVA:
        CONV['msgs'] = (CONV['msgs'] + [{'role': 'user', 'content': prep['pergunta']}, {'role': 'assistant', 'content': texto or '...'}])[-16:]
        CONV['t'] = time.time()
    try:
        pasta = os.path.join(vault, '01_Federacao', 'Conversas com o CIO')
        os.makedirs(pasta, exist_ok=True)
        p = os.path.join(pasta, date.today().isoformat() + '.md')
        novo = not os.path.exists(p)
        with open(p, 'a', encoding='utf-8') as f:
            if novo:
                f.write('# Conversa com o CIO · %s\n\nPelo Orbitus. Não é decisão formal: o que precisar decidir vai à Mesa.\n' % date.today().strftime('%d/%m/%Y'))
            f.write('\n## %s · Marcio\n%s\n\n**CIO:** %s\n' % (datetime.now().strftime('%H:%M'), prep['pergunta'], texto))
    except OSError as e:
        print('cio: não gravei a conversa', e)


def nova():
    with TRAVA:
        CONV['msgs'] = []
    return {'ok': True}


def levar_ao_1on1(wealth, corpo):
    """Despacho no INBOX.md do Wealth (Protocolo de Federação); o 1:1 de domingo processa e marca [processado em …]."""
    texto = re.sub(r'\s+', ' ', str(corpo.get('texto') or '')).strip()[:1200]
    if not texto:
        with TRAVA:
            ult = [m for m in CONV['msgs'] if m['role'] == 'user'][-1:] if CONV['msgs'] else []
        texto = ult[0]['content'][:1200] if ult else ''
    if not texto:
        raise ValueError('nada para levar ao 1:1')
    pasta = os.path.join(wealth, '_orbitus')
    if not os.path.isdir(pasta):
        raise ValueError('não achei _orbitus no Wealth Office')
    p = os.path.join(pasta, 'INBOX.md')
    with open(os.path.join(pasta, '.lock_inbox'), 'w') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            atual = _ler(p)
            ns = [int(n) for n in re.findall(r'^## D-AIW-(\d+)', atual, flags=re.M)]
            num = 'D-AIW-%03d' % ((max(ns) if ns else 0) + 1)
            bloco = ('\n\n## %s — Pergunta ao CIO pelo Orbitus — %s\n\n'
                     '**Contexto:** o investidor conversou com o CIO pelo Orbitus em %s (registro em '
                     '`Orbitus/01_Federacao/Conversas com o CIO/%s.md`) e pediu para levar o tema ao 1:1.\n\n'
                     '**Pedido:** %s\n\n'
                     '**Resposta esperada:** tratar no próximo 1:1 do CIO; se virar decisão, abrir na Mesa e registrar no Decision Journal. '
                     'Nada aqui autoriza execução de ordens.\n') % (num, date.today().isoformat(), datetime.now().strftime('%d/%m %H:%M'),
                                                                      date.today().isoformat(), texto)
            with open(p, 'a', encoding='utf-8') as f:
                f.write(bloco)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
    linha = num
    return {'ok': True, 'linha': linha.strip()}
