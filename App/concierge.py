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

SISTEMA = """Você é o Concierge do Orbitus, o painel pessoal do Marcio (São Paulo, 42 anos, consultor independente).
Você enxerga, no CONTEXTO abaixo, o que os sistemas dele já registraram: tarefas, agenda, viagens, treino e alimentação (com o parecer da Mesa da Saúde: personal e nutricionista), o AI Wealth Office (carteira, decisões da Mesa de investimentos, saúde das automações) e os e-mails que pedem resposta.

Como responder:
- Português do Brasil, direto, no máximo 4 frases curtas. A resposta pode ser lida em voz alta: nada de markdown, listas com símbolos, tabelas ou emojis. Números por extenso só quando ajudar a ouvir (ex.: "quatrocentos e oitenta mil reais").
- Responda primeiro o que foi perguntado; depois, se houver, um único próximo passo.
- Use só o que está no contexto. Se não estiver lá, diga que não sabe e onde ele pode ver. Não invente valores, datas nem pareceres.
- Você não executa ordens de compra ou venda, não manda e-mail e não altera nada. Para investimentos, relate o que a Mesa do Wealth decidiu ou recomenda; a decisão é dele.
- Saúde: sem diagnóstico nem remédio. Dor, tontura ou lesão: diga para parar e procurar um profissional.
- Se ele pedir para anotar ou criar tarefas, confirme numa frase e termine a resposta com uma linha por tarefa, exatamente assim: [[tarefa: texto da tarefa]] (com " 📅 AAAA-MM-DD" no fim do texto quando houver data).
- Seja honesto, inclusive quando o número não for bom."""


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


def _post(corpo, chave):
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
    'bom dia': ('Bom dia', 1100, """BRIEFING DA MANHÃ. Comece com "Bom dia, Marcio." e diga, nesta ordem e em frases curtas para ouvir:
1) o que está na agenda de hoje (horários);
2) as tarefas de hoje e as atrasadas, as mais importantes primeiro (no máximo 5, pelo nome curto);
3) quantos e-mails pedem resposta e de quem são os mais importantes;
4) o treino de hoje (nome da sessão, onde, e o que a Mesa da Saúde recomendou para hoje) e a meta de proteína;
5) se houver, o que o Wealth precisa de você hoje e a contagem das viagens;
Feche com uma frase de foco para o dia. No máximo 10 frases."""),
    'boa tarde': ('Boa tarde', 900, """BALANÇO DA TARDE. Comece com "Boa tarde, Marcio." e diga:
1) o que já foi feito hoje (tarefas concluídas hoje, treino registrado ou não, refeições e água registradas);
2) o que ainda falta hoje, em ordem de prioridade;
3) atualizações novas: e-mails que pedem resposta, decisões ou alertas do Wealth, viagens.
No máximo 8 frases."""),
    'boa noite': ('Boa noite', 1000, """FECHAMENTO DO DIA. Comece com "Boa noite, Marcio." e diga:
1) o resumo do dia: o que foi concluído, treino, alimentação (proteína e calorias registradas contra a meta);
2) o que ainda dá para fechar hoje (no máximo 3 itens rápidos, inclusive registrar o que falta no treino);
3) o que fica para amanhã: tarefas, compromissos da agenda e o treino de amanhã.
Feche com uma frase curta e gentil. No máximo 9 frases."""),
    'boa sexta': ('Boa sexta', 1100, """FECHAMENTO DA SEMANA (sexta-feira). Comece com "Boa sexta, Marcio." e diga:
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


def perguntar(pergunta, contexto, capturar=None):
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
    sistema = SISTEMA + '\n\nAgora: %s (%s).\n\nCONTEXTO (JSON, retrato do momento):\n%s' % (
        agora.strftime('%Y-%m-%d %H:%M'), ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'][agora.weekday()],
        json.dumps(contexto, ensure_ascii=False, separators=(',', ':'), default=str))
    rit = _ritual(pergunta)
    conteudo = pergunta if not rit else pergunta + '\n\n[' + rit[2] + ']'
    corpo = {'model': MODELO, 'max_tokens': rit[1] if rit else 700, 'system': sistema,
             'messages': hist + [{'role': 'user', 'content': conteudo}]}
    j = _post(corpo, chave)
    texto = ''.join(b.get('text', '') for b in j.get('content', []) if b.get('type') == 'text').strip()
    us = j.get('usage') or {}
    pi, po = PRECO.get(MODELO, (2.0, 10.0))
    custo = (us.get('input_tokens', 0) * pi + us.get('output_tokens', 0) * po) / 1e6
    criadas = []
    for t in re.findall(r'\[\[tarefa:\s*(.+?)\]\]', texto):
        t = t.strip()[:200]
        if capturar:
            try:
                capturar(t)
                criadas.append(t)
            except Exception as e:
                texto += ' (Não consegui criar a tarefa "%s": %s.)' % (t, e)
    texto = re.sub(r'\s*\[\[tarefa:.+?\]\]', '', texto).strip()
    tarefa = '; '.join(criadas) or None
    with TRAVA:
        u = _uso()
        u['usd'] = u.get('usd', 0) + custo
        u['perguntas'] = u.get('perguntas', 0) + 1
        _gravar_uso(u)
        CONVERSA['msgs'] = (CONVERSA['msgs'] + [{'role': 'user', 'content': pergunta}, {'role': 'assistant', 'content': texto or '...'}])[-12:]
        CONVERSA['t'] = time.time()
    return {'resposta': texto, 'tarefa': tarefa, 'custo_usd': round(custo, 4), 'mes_usd': round(u['usd'], 4),
            'teto': u.get('teto', TETO_PADRAO)}


def nova_conversa():
    with TRAVA:
        CONVERSA['msgs'] = []
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


def sintetizar(texto):
    """Devolve (bytes, tipo). Voz neural do Google se configurada; senão a voz do Mac."""
    voz = voz_escolhida() or ''
    if voz.startswith('google:'):
        t = re.sub(r'\s+', ' ', str(texto or '')).strip()[:4500]
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
