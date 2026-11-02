# -*- coding: utf-8 -*-
"""Orbitus — avisos (Web Push) no iPhone e no Mac, direto do próprio Orbitus.

Chaves VAPID: ~/.orbitus/vapid_privada.pem e ~/.orbitus/vapid_publica.txt (fora do cofre; criadas por App/instalar_push.sh).
Aparelhos inscritos: ~/.orbitus/push_inscricoes.json. Avisos já enviados: ~/.orbitus/push_enviados.json.
Precisa da biblioteca pywebpush (o instalador põe). Sem ela, o resto do Orbitus funciona normalmente.
O que avisa: lembretes de água e tarefas com hora (⏰), no horário, enquanto o Mac estiver ligado.
"""
import json, os, threading, time
from datetime import date, datetime, timedelta

DIR = os.path.expanduser('~/.orbitus')
PRIV = os.path.join(DIR, 'vapid_privada.pem')
PUB = os.path.join(DIR, 'vapid_publica.txt')
INSC = os.path.join(DIR, 'push_inscricoes.json')
ENV = os.path.join(DIR, 'push_enviados.json')
SUB = 'https://mac-mini.taila77abf.ts.net'   # contato exigido pelo serviço de push da Apple (sem e-mail pessoal)
TRAVA = threading.Lock()
ULTIMO = {'erro': '', 'enviado': ''}


def _ler(p, d):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def _gravar(p, obj):
    os.makedirs(DIR, exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def _lib():
    try:
        from pywebpush import webpush, WebPushException  # noqa
        return webpush, WebPushException
    except Exception:
        return None, None


def estado():
    webpush, _ = _lib()
    pub = ''
    try:
        pub = open(PUB, encoding='utf-8').read().strip()
    except OSError:
        pass
    return {'biblioteca': bool(webpush), 'chaves': bool(pub and os.path.exists(PRIV)), 'chave_publica': pub,
            'inscritos': len(_ler(INSC, [])), 'ultimo_erro': ULTIMO['erro'], 'ultimo_envio': ULTIMO['enviado'],
            'pronto': bool(webpush and pub and os.path.exists(PRIV))}


def inscrever(corpo):
    sub = corpo.get('sub') or {}
    if not isinstance(sub, dict) or not str(sub.get('endpoint', '')).startswith('https://') or not (sub.get('keys') or {}).get('p256dh'):
        raise ValueError('inscrição inválida')
    with TRAVA:
        L = [x for x in _ler(INSC, []) if x.get('endpoint') != sub['endpoint']]
        L.append({'endpoint': sub['endpoint'], 'keys': {'p256dh': sub['keys']['p256dh'], 'auth': sub['keys'].get('auth', '')},
                  'aparelho': str(corpo.get('aparelho') or '')[:60], 'em': datetime.now().isoformat(timespec='minutes')})
        _gravar(INSC, L[-10:])
    return {'ok': True, 'inscritos': len(L)}


def enviar(titulo, corpo, tag='orbitus', url='/'):
    webpush, WPE = _lib()
    if not webpush or not os.path.exists(PRIV):
        raise RuntimeError('push não instalado (rode App/instalar_push.sh)')
    dados = json.dumps({'titulo': titulo, 'corpo': corpo, 'tag': tag, 'url': url}, ensure_ascii=False)
    vivos, ok = [], 0
    for s in _ler(INSC, []):
        try:
            webpush(subscription_info={'endpoint': s['endpoint'], 'keys': s['keys']}, data=dados,
                    vapid_private_key=PRIV, vapid_claims={'sub': SUB}, ttl=3600, timeout=15)
            ok += 1
            vivos.append(s)
        except Exception as e:
            code = getattr(getattr(e, 'response', None), 'status_code', None)
            if code in (404, 410):
                continue            # aparelho desinscrito: some da lista
            vivos.append(s)
            ULTIMO['erro'] = '%s: %s' % (datetime.now().strftime('%d/%m %H:%M'), str(e)[:160])
    with TRAVA:
        _gravar(INSC, vivos)
    if ok:
        ULTIMO['enviado'] = datetime.now().strftime('%d/%m %H:%M') + ' · ' + titulo[:60]
    return {'ok': ok > 0, 'enviados': ok, 'aparelhos': len(vivos)}


def ciclo(montar_dia):
    """Laço do servidor: a cada 30 s olha a lista de hoje e avisa o que chegou na hora (até 10 min de atraso)."""
    while True:
        try:
            if estado()['pronto'] and _ler(INSC, []):
                agora = datetime.now()
                hoje = date.today().isoformat()
                hm, lim = agora.strftime('%H:%M'), (agora - timedelta(minutes=10)).strftime('%H:%M')
                env = _ler(ENV, {})
                env = {k: v for k, v in env.items() if v >= (date.today() - timedelta(days=2)).isoformat()}
                mudou = False
                dia = montar_dia(hoje)
                ag = dia.get('agua') or {}
                for i, (h, c, acum) in enumerate(ag.get('slots') or []):
                    # água: só avisa se você estiver atrás do ritmo naquele horário
                    if lim <= h <= hm and ag.get('bebidos', 0) < acum:
                        chave = hoje + '|a|' + h
                        if chave not in env:
                            env[chave] = hoje
                            mudou = True
                            try:
                                enviar('💧 Hidratação', 'Você está em %d de %d copos. Que tal um copo agora?' % (ag.get('bebidos', 0), ag.get('meta', 10)), 'agua', '/')
                            except Exception as e:
                                ULTIMO['erro'] = str(e)[:160]
                # rotinas do Wealth que falharam ou não rodaram no horário: um aviso por rotina por dia, com o motivo
                for r in (dia.get('wealth_rotinas') or {}).get('itens') or []:
                    if r.get('estado') != 'falha':
                        continue
                    chave = hoje + '|w|' + r.get('id', '')
                    if chave in env:
                        continue
                    env[chave] = hoje
                    mudou = True
                    try:
                        enviar('⚠️ Wealth · ' + r.get('nome', ''), r.get('texto', '')[:180], 'wealth-' + r.get('id', ''), '/')
                    except Exception as e:
                        ULTIMO['erro'] = str(e)[:160]
                for x in dia['itens']:
                    h = x.get('hora') or ''
                    if not h or x.get('feito') or not (lim <= h <= hm):
                        continue
                    if x['tipo'] == 'tarefa':
                        chave = hoje + '|t|' + x.get('texto', '')[:80] + '|' + h
                        tit, txt, tag = '⏰ ' + h + ' · ' + x.get('texto', '')[:90], 'Toque para abrir a lista do dia.', 'tarefa-' + h
                    else:
                        continue
                    if chave in env:
                        continue
                    env[chave] = hoje
                    mudou = True
                    try:
                        enviar(tit, txt, tag, '/')
                    except Exception as e:
                        ULTIMO['erro'] = str(e)[:160]
                if mudou:
                    _gravar(ENV, env)
        except Exception as e:
            ULTIMO['erro'] = 'ciclo: ' + str(e)[:160]
        time.sleep(30)
