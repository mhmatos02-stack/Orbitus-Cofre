# -*- coding: utf-8 -*-
"""Orbitus — Concierge: responde perguntas sobre tudo o que o Orbitus enxerga, usando a API do Claude.

Chave: Keychain do macOS (serviço "orbitus-anthropic", conta "api"); nunca no cofre.
Gasto: ~/.orbitus/concierge_uso.json (fora do cofre), com teto mensal em dólares.
Conversa: só na memória do servidor (últimas trocas, zera após 30 min parado). Nada é gravado no cofre.
Somente leitura, com uma exceção: criar tarefa quando o usuário pede.
"""
import json, os, re, subprocess, threading, time, urllib.error, urllib.request
from datetime import date, datetime

MODELO = os.environ.get('ORBITUS_CONCIERGE_MODELO', 'claude-sonnet-5-5')
PRECO = {'claude-sonnet-5-5': (2.0, 10.0), 'claude-haiku-5-5': (0.10, 0.50), 'claude-opus-5-5': (4.0, 20.0)}  # US$ por milhão (entrada, saída)
USO = os.path.expanduser('~/.orbitus/concierge_uso.json')
TETO_PADRAO = 15.0
TRAVA = threading.Lock()
CONVERSA = {'t': 0, 'msgs': []}
AGUA_FN = None
PESO_FN = None   # o servidor liga: grava o peso do dia no Treino   # o servidor liga: soma copos no contador de água do Treino quando ele diz que bebeu

SISTEMA = """Você é o Concierge do Orbitus, o painel pessoal do Marcio (São Paulo, 42 anos, consultor independente).
Você enxerga, no CONTEXTO abaixo, o que os sistemas dele já registraram: tarefas, agenda, viagens, treino e alimentação (com o parecer da Mesa da Saúde: personal e nutricionista), o AI Wealth Office (carteira, decisões da Mesa de investimentos, saúde das automações) e os e-mails que pedem resposta.

Como responder:
- Português do Brasil, direto, no máximo 4 frases curtas. A resposta pode ser lida em voz alta: nada de markdown, listas com símbolos, tabelas ou emojis. Números por extenso só quando ajudar a ouvir (ex.: "quatrocentos e oitenta mil reais").
- Responda primeiro o que foi perguntado; depois, se houver, um único próximo passo.
- Use só o que está no contexto. Se não estiver lá, diga que não sabe e onde ele pode ver. Não invente valores, datas nem pareceres.
- Você não executa ordens de compra ou venda, não manda e-mail e não altera nada. Para investimentos, relate o que a Mesa do Wealth decidiu ou recomenda; a decisão é dele.
- Saúde: sem diagnóstico nem remédio. Dor, tontura ou lesão: diga para parar e procurar um profissional.
- Se ele pedir para anotar ou criar tarefas, confirme numa frase e termine a resposta com uma linha por tarefa, exatamente assim: [[tarefa: texto da tarefa]] (com " 📅 AAAA-MM-DD" no fim do texto quando houver data e " ⏰ HH:MM" quando ele disser um horário).
- Seja honesto, inclusive quando o número não for bom.
- Hidratação (agua_hoje no contexto: bebidos, meta, esperado até agora, atrás): nos rituais, diga em uma frase como está a água. Nas outras respostas, só se ele estiver 2 copos ou mais atrás do ritmo, feche com uma frase curta e leve, variando: incentive a beber ou pergunte se bebeu água recentemente. Não repita isso se já falou de água nas últimas trocas, e nunca transforme em sermão.
- Se ele disser que bebeu água, confirme e termine com uma linha exatamente assim: [[agua: N]] (N = copos de 250 ml; meio litro = 2, uma garrafa de 1 litro = 4).
- Se ele disser quanto pesou hoje, confirme o número, compare com o último peso do contexto em uma frase (sem drama; o oficial é o de domingo) e termine com uma linha exatamente assim: [[peso: 80.9]]."""


def _chave():
    try:
        r = subprocess.run(['security', 'find-generic-password', '-s', 'orbitus-anthropic', '-a', 'api', '-w'],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _uso():
    try:
        with open(USO, encoding='utf-8') as f:
            u = json.load(f)
    except (OSError, ValueError):
        u = {}
    mes = date.today().strftime('%Y-%m')
    if u.get('mes') != mes:
        u = {'mes': mes, 'usd': 0.0, 'perguntas': 0, 'teto': u.get('teto', TETO_PADRAO)}
    return u


def _gravar_uso(u):
    os.makedirs(os.path.dirname(USO), exist_ok=True)
    tmp = USO + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(u, f)
    os.replace(tmp, USO)


def estado():
    u = _uso()
    return {'configurado': bool(_chave()), 'modelo': MODELO, 'mes': u['mes'], 'usd': round(u['usd'], 4),
            'teto': u.get('teto', TETO_PADRAO), 'perguntas': u.get('perguntas', 0)}


def _sem_ajustes(corpo):
    return {k: v for k, v in corpo.items() if k not in ('thinking', 'output_config')}


def _post(corpo, chave, _tentou=False):
    dados = json.dumps(corpo).encode('utf-8')
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=dados, method='POST', headers={
        'content-type': 'application/json', 'x-api-key': chave, 'anthropic-version': '2023-06-01'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode('utf-8')).get('error', {}).get('message', '')
        except Exception:
            msg = ''
        if e.code == 400 and not _tentou and ('thinking' in corpo or 'output_config' in corpo):
            return _post(_sem_ajustes(corpo), chave, True)
        raise RuntimeError('a API respondeu %s%s' % (e.code, ': ' + msg if msg else ''))
    except urllib.error.URLError:
        # mesmo plano B da agenda: o curl do sistema usa os certificados do macOS
        r = subprocess.run(['/usr/bin/curl', '-sS', '--max-time', '60', 'https://api.anthropic.com/v1/messages',
                            '-H', 'content-type: application/json', '-H', 'x-api-key: ' + chave,
                            '-H', 'anthropic-version: 2023-06-01', '--data-binary', '@-'],
                           input=dados, capture_output=True, timeout=70)
        j = json.loads(r.stdout.decode('utf-8') or '{}')
        if j.get('type') == 'error':
            raise RuntimeError('a API respondeu: ' + j.get('error', {}).get('message', 'erro'))
        return j


RITUAIS = {
    'bom dia': ('Bom dia', 4000, """BRIEFING DA MANHÃ. Comece com "Bom dia, Marcio." e diga, nesta ordem e em frases curtas para ouvir:
1) o que está na agenda de hoje (horários);
2) a lista do dia em ordem de horário (lista_do_dia: rotina, tarefas com hora e compromissos), dizendo o horário de cada item; depois as atrasadas, se houver (no máximo 7 itens no total);
3) quantos e-mails pedem resposta e de quem são os mais importantes;
4) o treino de hoje (nome da sessão, onde, e o que a Mesa da Saúde recomendou para hoje) e a meta de proteína;
5) se houver, o que o Wealth precisa de você hoje e a contagem das viagens;
Feche com uma frase de foco para o dia. No máximo 10 frases."""),
    'boa tarde': ('Boa tarde', 4000, """BALANÇO DA TARDE. Comece com "Boa tarde, Marcio." e diga:
1) o que já foi feito hoje (itens marcados na lista_do_dia, tarefas concluídas, treino registrado ou não, refeições e água);
2) o que ainda falta hoje, em ordem de prioridade;
3) atualizações novas: e-mails que pedem resposta, decisões ou alertas do Wealth, viagens.
No máximo 8 frases."""),
    'boa noite': ('Boa noite', 4000, """FECHAMENTO DO DIA. Comece com "Boa noite, Marcio." e diga:
1) o resumo do dia: o que foi concluído, treino, alimentação (proteína e calorias registradas contra a meta);
2) o que ainda dá para fechar hoje (no máximo 3 itens rápidos, inclusive registrar o que falta no treino);
3) o que fica para amanhã: tarefas, compromissos da agenda e o treino de amanhã.
Feche com uma frase curta e gentil. No máximo 9 frases."""),
    'boa sexta': ('Boa sexta', 4000, """FECHAMENTO DA SEMANA (sexta-feira). Comece com "Boa sexta, Marcio." e diga:
1) o balanço da semana: tarefas concluídas, treinos feitos contra o alvo, cintura e peso se houver, decisões do Wealth;
2) o que fica para o fim de semana (incluindo treino de sábado e a corrida e ioga de domingo, pesagem e cintura no domingo, local de treino);
3) o que já está marcado para a próxima semana (agenda, tarefas com prazo, ações da Mesa, viagens).
Termine perguntando exatamente: "Tem algo que você quer acrescentar para o fim de semana ou para a próxima semana?". No máximo 11 frases.
Se na mensagem seguinte ele listar itens, crie uma tarefa para cada um (uma linha [[tarefa: ...]] por item, com a data em AAAA-MM-DD depois de " 📅 " quando ele disser o dia)."""),
}


def _ritual(pergunta):
    n = re.sub(r'[^a-z ]', '', re.sub(r'[\u0300-\u036f]', '', __import__('unicodedata').normalize('NFD', pergunta.lower())))
    n = re.sub(r'\s+', ' ', n).strip()
    for k, v in RITUAIS.items():
        if n.startswith(k) and ('orbitus' in n or n == k):
            return v
    return None


TOPICOS = {
    'financas': r'wealth|carteira|invest|patrim|a[cç][aã]o|a[cç][oõ]es|\bfii|fundo|dividend|provento|\brenda\b|caixa|reserva|decis|bolsa|ibov|selic|copom|cdb|tesouro|aporte|rebalanc|imposto|isen[cç]|ticker|cota|juros|d[oó]lar|mesa de invest|\b[a-z]{4}\d{1,2}\b',
    'treino': r'treino|trein|exerc|academia|corrid|correr|\bremo\b|ioga|yoga|pilates|\bpeso\b|pesar|cintura|passo|prote[ií]n|caloria|kcal|refei|comi|aliment|dieta|[aá]gua|nutri|personal|sa[uú]de|sono|dormi|almo[cç]|jantar|caf[eé] da manh|lanche|shape|medida|muscula',
    'viagem': r'viag|viaj|praia|forte|salvador|alemanha|stuttgart|lenk|su[ií][cç]a|\bvoo|v[oô]o|mala|bagagem|passaporte|hotel|iberostar|\bgol\b|presente|aeroporto|embarque|roteiro|f[eé]rias',
    'emails': r'e-?mail|mensage|responder|resposta|inbox|caixa de entrada|escrever para|retornar',
    'agenda': r'agenda|reuni|compromisso|calend[aá]rio|evento|marcad|hor[aá]rio|amanh|depois de amanh|pr[oó]xima semana|segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo',
    'tarefas': r'tarefa|pend[eê]n|fazer|to-?do|lista|atrasad|conclu|feito|fiz\b|priorid|anot|lembr',
}


def _sem_acento(t):
    import unicodedata
    return re.sub(r'[̀-ͯ]', '', unicodedata.normalize('NFD', str(t or '').lower()))


def intencoes(pergunta):
    """Seções do contexto que a pergunta pede. None = mandar tudo (rituais e perguntas sem tema claro).
    Pergunta curta no meio de uma conversa herda os temas da anterior ("e a de amanhã?")."""
    if _ritual(pergunta):
        return None
    q = str(pergunta or '').lower()
    achou = {k for k, rx in TOPICOS.items() if re.search(rx, q) or re.search(rx, _sem_acento(q))}
    with TRAVA:
        ativa = time.time() - CONVERSA['t'] <= 1800 and CONVERSA['msgs']
        antes = set(CONVERSA.get('secoes') or ()) if ativa else set()
        anterior_tudo = ativa and CONVERSA.get('secoes') is None
    if not achou:
        if anterior_tudo or not antes:
            return None
        return antes
    if len(q) <= 60 and ativa and not anterior_tudo:
        achou |= antes
    return achou


def preparar(pergunta, contexto, secoes='?'):
    """Valida, confere chave e teto e monta o corpo do pedido. Erros aqui viram 400 antes de começar a resposta."""
    pergunta = re.sub(r'\s+', ' ', str(pergunta or '')).strip()[:1500]
    if not pergunta:
        raise ValueError('faça uma pergunta')
    chave = _chave()
    if not chave:
        raise ValueError('chave da API não configurada. No Terminal: security add-generic-password -U -s orbitus-anthropic -a api -w')
    with TRAVA:
        u = _uso()
        if u['usd'] >= u.get('teto', TETO_PADRAO):
            raise ValueError('teto do mês atingido (US$ %.2f). Aumente em ~/.orbitus/concierge_uso.json, campo "teto".' % u.get('teto', TETO_PADRAO))
        if time.time() - CONVERSA['t'] > 1800:
            CONVERSA['msgs'] = []
        hist = CONVERSA['msgs'][-8:]
    agora = datetime.now()
    recorte = '' if secoes in ('?', None) else '\nRecorte do contexto para esta pergunta: %s. Se a resposta depender de algo fora do recorte, diga que precisa olhar e sugira perguntar de novo citando o assunto.' % ', '.join(sorted(secoes))
    sistema = SISTEMA + recorte + '\n\nAgora: %s (%s).\n\nCONTEXTO (JSON, retrato do momento):\n%s' % (
        agora.strftime('%Y-%m-%d %H:%M'), ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'][agora.weekday()],
        json.dumps(contexto, ensure_ascii=False, separators=(',', ':'), default=str))
    rit = _ritual(pergunta)
    conteudo = pergunta if not rit else pergunta + '\n\n[' + rit[2] + ']'
    corpo = {'model': MODELO, 'max_tokens': rit[1] if rit else 3000, 'system': sistema,
             'messages': hist + [{'role': 'user', 'content': conteudo}],
             # Concierge é leitura de contexto, não problema difícil: sem raciocínio prévio a voz começa antes e o texto não trava no meio
             'thinking': {'type': 'between_tools'}, 'output_config': {'effort': 'low'}}
    return {'pergunta': pergunta, 'chave': chave, 'corpo': corpo, 'secoes': None if secoes == '?' else secoes}


def _visivel(texto):
    """Texto que pode ir para a tela/voz: sem as linhas [[tarefa: ...]] e sem um marcador ainda incompleto no fim."""
    t = re.sub(r'\s*\[\[(?:tarefa|agua|peso):.*?\]\]', '', texto, flags=re.S)
    i = t.find('[[')
    if i >= 0:
        t = t[:i]
    elif t.endswith('['):
        t = t[:-1]
    return t


def _finalizar(prep, texto, us, capturar):
    pi, po = PRECO.get(MODELO, (2.0, 10.0))
    custo = (us.get('input_tokens', 0) * pi + us.get('output_tokens', 0) * po) / 1e6
    criadas = []
    for t in re.findall(r'\[\[tarefa:\s*(.+?)\]\]', texto, flags=re.S):
        t = re.sub(r'\s+', ' ', t).strip()[:200]
        if capturar:
            try:
                capturar(t)
                criadas.append(t)
            except Exception as e:
                texto += ' (Não consegui criar a tarefa "%s": %s.)' % (t, e)
    texto = re.sub(r'\s*\[\[tarefa:.+?\]\]', '', texto, flags=re.S).strip()
    copos = sum(int(n) for n in re.findall(r'\[\[agua:\s*(-?\d{1,2})\s*\]\]', texto))
    texto = re.sub(r'\s*\[\[agua:.*?\]\]', '', texto, flags=re.S).strip()
    peso = None
    mp = re.search(r'\[\[peso:\s*(\d{2,3}(?:[.,]\d{1,2})?)\s*\]\]', texto)
    texto = re.sub(r'\s*\[\[peso:.*?\]\]', '', texto, flags=re.S).strip()
    if mp and PESO_FN:
        try:
            peso = PESO_FN(float(mp.group(1).replace(',', '.')))
        except Exception as e:
            texto += ' (Não consegui registrar o peso: %s.)' % e
    agua = None
    if copos and AGUA_FN:
        try:
            agua = AGUA_FN(copos)
        except Exception as e:
            texto += ' (Não consegui somar a água: %s.)' % e
    with TRAVA:
        u = _uso()
        u['usd'] = u.get('usd', 0) + custo
        u['perguntas'] = u.get('perguntas', 0) + 1
        _gravar_uso(u)
        CONVERSA['msgs'] = (CONVERSA['msgs'] + [{'role': 'user', 'content': prep['pergunta']}, {'role': 'assistant', 'content': texto or '...'}])[-12:]
        CONVERSA['t'] = time.time()
        CONVERSA['secoes'] = sorted(prep['secoes']) if prep.get('secoes') is not None else None
    return {'resposta': texto, 'tarefa': '; '.join(criadas) or None, 'agua': agua, 'peso': peso, 'custo_usd': round(custo, 4), 'mes_usd': round(u['usd'], 4),
            'teto': u.get('teto', TETO_PADRAO), 'tokens_entrada': us.get('input_tokens', 0),
            'recorte': prep.get('secoes') if prep.get('secoes') is None else sorted(prep['secoes'])}


def perguntar(pergunta, contexto, capturar=None, secoes='?'):
    """Resposta inteira de uma vez (usada como plano B e por quem não precisa de streaming)."""
    prep = preparar(pergunta, contexto, secoes)
    j = _post(prep['corpo'], prep['chave'])
    texto = ''.join(b.get('text', '') for b in j.get('content', []) if b.get('type') == 'text').strip()
    return _finalizar(prep, texto, j.get('usage') or {}, capturar)


def _eventos_sse(linhas):
    """Lê o SSE da API (linhas em bytes) e devolve os eventos JSON."""
    for raw in linhas:
        l = raw.decode('utf-8', 'replace').strip()
        if l.startswith('data:'):
            try:
                yield json.loads(l[5:].strip())
            except ValueError:
                continue


def _stream(corpo, chave, _tentou=False, espera=60):
    corpo = dict(corpo, stream=True)
    dados = json.dumps(corpo).encode('utf-8')
    hdr = {'content-type': 'application/json', 'x-api-key': chave, 'anthropic-version': '2023-06-01', 'accept': 'text/event-stream'}
    try:
        r = urllib.request.urlopen(urllib.request.Request('https://api.anthropic.com/v1/messages', data=dados, method='POST', headers=hdr), timeout=espera)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode('utf-8')).get('error', {}).get('message', '')
        except Exception:
            msg = ''
        if e.code == 400 and not _tentou and ('thinking' in corpo or 'output_config' in corpo):
            print('concierge: API recusou thinking/effort (%s); seguindo sem' % msg[:120])
            yield from _stream(_sem_ajustes(corpo), chave, True, espera)
            return
        raise RuntimeError('a API respondeu %s%s' % (e.code, ': ' + msg if msg else ''))
    except urllib.error.URLError:
        r = None
    if r is not None:
        with r:
            for ev in _eventos_sse(r):
                yield ev
        return
    # plano B: curl do sistema (certificados do macOS), também em streaming
    p = subprocess.Popen(['/usr/bin/curl', '-sS', '-N', '--max-time', str(max(90, espera * 3)), 'https://api.anthropic.com/v1/messages',
                          '-H', 'content-type: application/json', '-H', 'x-api-key: ' + chave,
                          '-H', 'anthropic-version: 2023-06-01', '--data-binary', '@-'],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.stdin.write(dados)
    p.stdin.close()
    try:
        primeiro = True
        for raw in p.stdout:
            if primeiro and raw.strip().startswith(b'{'):
                j = json.loads(raw.decode('utf-8') or '{}')
                raise RuntimeError('a API respondeu: ' + (j.get('error') or {}).get('message', 'erro'))
            primeiro = False
            for ev in _eventos_sse([raw]):
                yield ev
    finally:
        p.stdout.close()
        p.wait(timeout=5)


def perguntar_fluxo(prep, capturar=None):
    """Gera a resposta aos pedaços: {'t':'delta','x':texto} ... e por fim {'t':'fim', ...igual a perguntar()}."""
    texto, enviado, us = '', '', {}
    for ev in _stream(prep['corpo'], prep['chave']):
        tp = ev.get('type')
        if tp == 'message_start':
            us.update((ev.get('message') or {}).get('usage') or {})
        elif tp == 'content_block_delta' and (ev.get('delta') or {}).get('type') == 'text_delta':
            texto += ev['delta'].get('text', '')
            vis = _visivel(texto)
            if len(vis) > len(enviado) and vis.startswith(enviado):
                yield {'t': 'delta', 'x': vis[len(enviado):]}
                enviado = vis
        elif tp == 'message_delta':
            us.update(ev.get('usage') or {})
            if (ev.get('delta') or {}).get('stop_reason'):
                us['_parou'] = ev['delta']['stop_reason']
        elif tp == 'error':
            raise RuntimeError('a API respondeu: ' + (ev.get('error') or {}).get('message', 'erro'))
    parou = us.pop('_parou', '')
    if parou == 'max_tokens':
        texto = texto.rstrip() + '… (a resposta passou do limite e foi cortada; peça para continuar)'
        yield {'t': 'delta', 'x': '… (a resposta passou do limite e foi cortada; peça para continuar)'}
    fim = _finalizar(prep, texto.strip(), us, capturar)
    fim['t'] = 'fim'
    fim['parou'] = parou
    fim['tokens_saida'] = us.get('output_tokens', 0)
    yield fim


def nova_conversa():
    with TRAVA:
        CONVERSA['msgs'] = []
        CONVERSA['secoes'] = None
    return {'ok': True}


# ---------------------------------------------------------------- voz do Mac (local, sem custo)
VOZ_CFG = os.path.expanduser('~/.orbitus/voz.txt')   # opcional: nome exato de uma voz para forçar


def vozes():
    """Vozes pt-BR instaladas no macOS, da melhor para a pior (Premium > Aprimorada/Enhanced > padrão)."""
    try:
        r = subprocess.run(['say', '-v', '?'], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for l in r.stdout.splitlines():
        m = re.match(r'^(.+?)\s+(pt[_-]BR)\b', l)
        if m:
            nome = m.group(1).strip()
            nota = 3 if 'Premium' in nome else 2 if re.search(r'Enhanced|Aprimorad|Melhorad', nome) else 1
            out.append((nota, nome))
    out.sort(key=lambda x: -x[0])
    return [n for _, n in out]


CFG_COFRE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '00_Sistema', 'concierge.json')


def voz_escolhida():
    """'sistema' = voz do sistema do macOS (a única forma de usar as vozes da Siri)."""
    try:
        with open(CFG_COFRE, encoding='utf-8') as f:
            v = (json.load(f).get('voz') or '').strip()
        if v:
            return v
    except (OSError, ValueError):
        pass
    try:
        v = open(VOZ_CFG, encoding='utf-8').read().strip()
        if v:
            return v
    except OSError:
        pass
    vs = vozes()
    return vs[0] if vs else None


def _google_tts(texto, voz):
    """Google Cloud Text-to-Speech (voz neural). voz = 'google:pt-BR-Chirp3-HD-Aoede'. Chave no Keychain: orbitus-google-tts / api."""
    try:
        chave = subprocess.run(['security', 'find-generic-password', '-s', 'orbitus-google-tts', '-a', 'api', '-w'],
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        chave = ''
    if not chave:
        raise RuntimeError('chave do Google TTS não configurada')
    nome = voz.split(':', 1)[1] or 'pt-BR-Chirp3-HD-Aoede'
    corpo = json.dumps({'input': {'text': texto}, 'voice': {'languageCode': 'pt-BR', 'name': nome},
                        'audioConfig': {'audioEncoding': 'MP3', 'speakingRate': 1.05}}).encode('utf-8')
    url = 'https://texttospeech.googleapis.com/v1/text:synthesize?key=' + chave
    try:
        req = urllib.request.Request(url, data=corpo, method='POST', headers={'content-type': 'application/json'})
        with urllib.request.urlopen(req, timeout=40) as r:
            j = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise RuntimeError('Google TTS respondeu %s: %s' % (e.code, e.read().decode('utf-8', 'replace')[:200]))
    except urllib.error.URLError:
        r = subprocess.run(['/usr/bin/curl', '-sS', '--max-time', '40', url, '-H', 'content-type: application/json', '--data-binary', '@-'],
                           input=corpo, capture_output=True, timeout=50)
        j = json.loads(r.stdout.decode('utf-8') or '{}')
    if 'audioContent' not in j:
        raise RuntimeError('Google TTS: ' + json.dumps(j.get('error', j))[:200])
    import base64
    return base64.b64decode(j['audioContent']), 'audio/mpeg'


MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
SIGLAS = [  # (padrão, como falar) — só o que a voz costuma errar
    (r'\bMarcio\b', 'Márcio'), (r'\bMARCIO\b', 'Márcio'),
    (r'\bFIIs\b', 'fiis'), (r'\bFII\b', 'fii'), (r'\bIR\b', 'imposto de renda'), (r'\bD-1\b', 'dê menos um'),
    (r'\bGRU\b', 'Guarulhos'), (r'\bSSA\b', 'Salvador'), (r'\bCGH\b', 'Congonhas'),
    (r'\bkm\b', 'quilômetros'), (r'\bkcal\b', 'calorias'), (r'\bkg\b', 'quilos'), (r'\bml\b', 'mililitros'),
    (r'\bvs\.?(?=\s)', 'contra'), (r'\bp/\s*', 'para '), (r'\bc/\s*', 'com '), (r'\bobs\.?:?', 'observação:'),
    (r'\s*(?:→|->)\s*', ' para '),
]


def _data_falada(m):
    a, mes, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mes <= 12 and 1 <= d <= 31):
        return m.group(0)
    txt = ('primeiro' if d == 1 else str(d)) + ' de ' + MESES[mes - 1]
    return txt if a == date.today().year else txt + ' de ' + str(a)


def para_fala(texto):
    """Ajusta o texto só para a voz (a tela continua igual): tira markdown, emojis e marcadores,
    acerta o nome e as siglas que o TTS lê errado, e fala datas e unidades por extenso."""
    t = str(texto or '')
    t = re.sub(r'\[\[(?:tarefa|agua|peso):.*?\]\]', '', t, flags=re.S)
    t = re.sub(r'https?://\S+', 'o link', t)
    t = re.sub(r'(?m)^\s*(?:[-*•]|\d+[.)])\s+', '', t)          # marcadores de lista
    t = re.sub(r'[*_#`>|~]+', '', t)                              # markdown
    t = re.sub(r'[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]', '', t)  # emojis
    t = re.sub(r'\b(\d{4})-(\d{2})-(\d{2})\b', _data_falada, t)
    t = re.sub(r'(\d)\s?g\b', r'\1 gramas', t)
    t = re.sub(r'(\d)\s?min\b', r'\1 minutos', t)
    t = re.sub(r'(\d)\s?h\b', r'\1 horas', t)
    t = re.sub(r'(\d{1,2})h(\d{2})\b', r'\1 e \2', t)
    t = re.sub(r'(\d)\s?x\s?(\d)', r'\1 por \2', t)
    t = re.sub(r'R\$\s?-\s?', 'menos R$ ', t)
    for rx, fala in SIGLAS:
        t = re.sub(rx, fala, t)
    t = re.sub(r'\s*\n+\s*', '. ', t)
    t = re.sub(r'\.\s*\.', '.', t)
    return re.sub(r'\s+', ' ', t).strip()


def sintetizar(texto):
    """Devolve (bytes, tipo). Voz neural do Google se configurada; senão a voz do Mac."""
    voz = voz_escolhida() or ''
    texto = para_fala(texto)
    if voz.startswith('google:'):
        t = texto[:4500]
        if not t:
            raise ValueError('sem texto')
        try:
            return _google_tts(t, voz)
        except RuntimeError as e:
            print('voz: Google falhou, usando a do Mac:', e)
            return _sintetizar_mac(texto, 'sistema'), 'audio/mp4'
    return _sintetizar_mac(texto, voz), 'audio/mp4'


def _sintetizar_mac(texto, voz=None):
    """Gera áudio AAC (.m4a) com a melhor voz pt-BR instalada. Devolve bytes."""
    texto = re.sub(r'\s+', ' ', str(texto or '')).strip()[:2500]
    if not texto:
        raise ValueError('sem texto')
    voz = voz or voz_escolhida()
    if not voz or voz.startswith('google:'):
        voz = 'sistema'
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        arq = os.path.join(d, 'r.m4a')
        cmd = ['say'] + ([] if voz == 'sistema' else ['-v', voz]) + ['--file-format=m4af', '--data-format=aac', '-o', arq]
        r = subprocess.run(cmd,
                           input=texto, text=True, capture_output=True, timeout=60)
        if r.returncode != 0 or not os.path.exists(arq):
            raise RuntimeError('say falhou: ' + (r.stderr or '').strip()[:200])
        with open(arq, 'rb') as f:
            return f.read()
