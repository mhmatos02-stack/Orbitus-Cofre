# -*- coding: utf-8 -*-
"""Orbitus — ponte entre o plano do AI Wealth Office e o Tarefas (aprovado em 09/11/2026).

Regras:
1. Quem libera uma ordem é o Wealth. Se o passo do plano trouxer `liberada` (e `bloqueio`), vale o que ele disser.
   Sem esses campos, vale o status do plano completo do Wealth: "agora" vira tarefa (com "confira a condição" se houver
   condição); "proximo"/"futuro" ficam na fila (regra de 11/11/2026).
2. Tarefa nascida do plano leva o id do passo na linha ("· plano p08") e é reconciliada a cada carga:
   data nova no plano -> data nova na tarefa; feito no Wealth -> tarefa concluída; bloqueada com a janela aberta
   -> volta para a fila; fora do plano -> arquivada. Tudo registrado em 00_Sistema/wealth_reconciliacao.jsonl.
3. Marcar uma tarefa do plano como feita avisa o Wealth pelo canal oficial (respostas.jsonl); desmarcar desfaz.
"""
import json, os, re, threading, time
from datetime import date, datetime

import mesa
import tarefas_api as T

_ULTIMA = {'t': 0.0}
_STATUS = {}
_TRAVA = threading.Lock()
VERBO = {'COMPRA': 'COMPRAR', 'VENDA': 'VENDER'}


def _norm(s):
    s = re.sub(r'\s*·\s*rode a pr[eé]-ordem.*$', '', str(s or ''), flags=re.I)
    return re.sub(r'[^a-z0-9]', '', T._sa(s))


def _br(iso):
    try:
        d = date.fromisoformat(str(iso)[:10])
        return '%02d/%02d' % (d.day, d.month)
    except ValueError:
        return ''


def _status_wealth(vault):
    """Status de cada passo no plano completo do Wealth (00_System/.automation_state/plano.json): agora, proximo,
    futuro, feito. A cópia em _orbitus/mesa só traz "pendente". Só leitura; {} se o arquivo faltar."""
    if not vault:
        return {}
    p = os.path.join(mesa.pasta_wealth(vault), '00_System', '.automation_state', 'plano.json')
    try:
        mt = os.path.getmtime(p)
    except OSError:
        return {}
    if _STATUS.get('p') == p and _STATUS.get('mt') == mt:
        return _STATUS['st']
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        st = {x['id']: str(x.get('status') or '') for x in d.get('passos') or [] if x.get('id')}
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    _STATUS.update(p=p, mt=mt, st=st)
    return st


def liberacao(p, vault=None):
    """(liberada, bloqueio) de um passo do plano.
    Regra de 11/11/2026 (Marcio): o passo que o Wealth marca como "agora" vira tarefa, mesmo com condição escrita;
    nesse caso o título leva "confira a condição" e o motivo diz qual é. Ordem com condição em "proximo"/"futuro"
    fica na fila. Ordem sem condição e passo que não é ordem seguem como antes (viram tarefa na data da janela).
    O campo `liberada` do Wealth, se um dia existir, continua mandando."""
    if 'liberada' in p:
        return bool(p.get('liberada')), str(p.get('bloqueio') or '')
    cond = str(p.get('condicao') or '').strip()
    if p.get('tipo') != 'ordem' or not cond:
        return True, ''
    st = _status_wealth(vault).get(p.get('id'))
    if st == 'agora':
        return True, ''
    if st in ('proximo', 'futuro'):
        return False, 'o Wealth marca como %s (janela %s); condição: %s' % (
            'próximo' if st == 'proximo' else 'futuro', _br(p.get('inicio')), cond)
    return False, 'o Wealth ainda não confirmou: ' + cond


def titulo(p):
    """Ordem com o lado em destaque: 'VENDER CMIG4 — lote 1 (1.500 ações)'."""
    a = re.sub(r'\s+', ' ', str(p.get('acao') or '')).strip()
    v = VERBO.get(str(p.get('operacao') or '').upper())
    if p.get('tipo') != 'ordem' or not v:
        return a
    a2 = re.sub(r'^(comprar|vender)\b\s*', '', a, flags=re.I)
    q = str(p.get('quantidade') or '').strip()
    if q and re.sub(r'\D', '', q) not in re.sub(r'\D', '', a2):
        a2 = '%s %s' % ('{:,}'.format(int(float(q))).replace(',', '.') if re.fullmatch(r'[\d.]+', q) else q, a2)
    t = '%s %s · rode a pré-ordem' % (v, a2)
    if str(p.get('condicao') or '').strip():
        t += ' · confira a condição'
    return t


def motivo(p):
    partes = []
    if p.get('tipo') == 'ordem' and p.get('condicao'):
        partes.append('CONFIRA ANTES: ' + p['condicao'])
    if p.get('inicio'):
        partes.append('janela ' + _br(p['inicio']) + ('–' + _br(p['fim']) if p.get('fim') and p['fim'] != p['inicio'] else ''))
    if p.get('valor_estimado'):
        try:
            partes.append('~R$ ' + '{:,.0f}'.format(float(p['valor_estimado'])).replace(',', '.'))
        except ValueError:
            pass
    if p.get('condicao') and p.get('tipo') != 'ordem':
        partes.append('condição: ' + p['condicao'])
    if p.get('tipo') == 'ordem':
        partes.append(p.get('aviso') or 'rode a pré-ordem antes de enviar; se ela der vermelho, confira com o CIO antes')
    return ' · '.join(partes)


def _passo_da_tarefa(f, plano):
    m = re.search(r'\bplano (p\d+)\b', f.get('fonte') or '')
    if m:
        return m.group(1), plano.get(m.group(1))
    if 'Wealth' not in (f.get('fonte') or ''):
        return None, None
    n = _norm(f['titulo'])
    for pid, p in plano.items():
        if p.get('quem') == 'voce' and n and (n == _norm(p.get('acao')) or n == _norm(titulo(p))):
            return pid, p
    return None, None


def _log(vault, ev):
    p = os.path.join(vault, '00_Sistema', 'wealth_reconciliacao.jsonl')
    ev['em'] = datetime.now().isoformat(timespec='seconds')
    with open(p, 'a', encoding='utf-8') as f:
        f.write(json.dumps(ev, ensure_ascii=False) + '\n')


def _respondidos(vault):
    """Passos do plano que você já marcou feito pela Mesa (pendentes ou já aplicados)."""
    w = os.path.join(mesa.pasta_wealth(vault), '_orbitus', 'mesa')
    out = {}
    for n in ('respostas.jsonl', 'respostas_arquivo.jsonl'):
        try:
            for l in open(os.path.join(w, n), encoding='utf-8'):
                try:
                    r = json.loads(l)
                except ValueError:
                    continue
                if r.get('tipo') == 'plano':
                    out[r.get('id')] = r.get('acao')
        except OSError:
            pass
    return out


def reconciliar(vault, plano=None, forcar=False):
    """Acerta as tarefas abertas com o plano. Devolve a lista do que mudou. Roda no máximo 1x por minuto."""
    if not forcar and time.time() - _ULTIMA['t'] < 60:
        return []
    if not _TRAVA.acquire(blocking=False):
        return []
    try:
        _ULTIMA['t'] = time.time()
        if plano is None:
            e = mesa.estado(vault)
            if not e.get('disponivel'):
                return []
            plano = {p['id']: p for p in e.get('plano') or []}
        hoje = date.today().isoformat()
        mudou = []
        pa = T._arq_principal(vault)
        with T.TRAVA:
            for raiz, _, arqs in os.walk(os.path.join(vault, '10_Tarefas')):
                for a in sorted(arqs):
                    if not a.endswith('.md'):
                        continue
                    caminho = os.path.join(raiz, a)
                    linhas = T._ler(caminho)
                    alterado, arquivar = False, []
                    for i, l in enumerate(linhas):
                        f = T.ler_linha(l)
                        if not f or f['feito'] or f['cancelada']:
                            continue
                        pid, p = _passo_da_tarefa(f, plano)
                        if not pid:
                            continue
                        novo = dict(f)
                        if 'plano ' + pid not in (f['fonte'] or ''):
                            novo['fonte'] = re.sub(r'·\s*plano\s*$', '', f['fonte']).rstrip(' ·') + ' · plano ' + pid
                        if p is None or p.get('status') in ('cancelado', 'cancelada'):
                            arquivar.append((i, 'saiu do plano do Wealth'))
                            continue
                        if p.get('status') == 'feito':
                            novo['feita_em'] = (p.get('executado_em') or hoje)[:10]
                            linhas[i] = T.montar_linha(novo, 'x')
                            mudou.append({'ev': 'concluida', 'passo': pid, 'tarefa': f['titulo']})
                            alterado = True
                            continue
                        lib, bloq = liberacao(p, vault)
                        ini = (p.get('inicio') or '')[:10]
                        if ini and ini > hoje and f['due'] != ini:
                            mudou.append({'ev': 'nova_data', 'passo': pid, 'tarefa': f['titulo'], 'de': f['due'], 'para': ini})
                            novo['due'] = ini
                        elif not lib and (not f['due'] or f['due'] <= hoje):
                            arquivar.append((i, 'voltou para a fila: ' + bloq))
                            continue
                        if novo != f:
                            linhas[i] = T.montar_linha(novo, ' ')
                            alterado = True
                    for i, porque in reversed(arquivar):
                        f = T.ler_linha(linhas[i])
                        pid, _ = _passo_da_tarefa(f, plano)
                        f['removida_em'] = hoje
                        arq = T.montar_linha(f, '-')
                        del linhas[i]
                        alvo = linhas if caminho == pa else T._ler(pa)
                        alvo.insert(T._secao(alvo, 'Arquivo'), arq)
                        if alvo is not linhas:
                            T._gravar(pa, alvo)
                        _esquecer_sugestao(vault, pid)
                        mudou.append({'ev': 'arquivada', 'passo': pid, 'tarefa': f['titulo'], 'porque': porque})
                        alterado = True
                    if alterado:
                        T._gravar(caminho, linhas)
        for m in mudou:
            _log(vault, m)
        return mudou
    finally:
        _TRAVA.release()


def _esquecer_sugestao(vault, pid):
    """Tira o 'já aceitei' da sugestão do passo, para ela voltar quando o Wealth liberar."""
    if not pid:
        return
    sid = T._sid('Mesa do Wealth', 'plano:' + pid)
    p = T._sug_arq(vault)
    est = T._sug_estado(vault)
    if est.pop(sid, None) is not None:
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(est, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)


def feitas_sem_registro(vault, plano):
    """Tarefas do plano que você marcou feitas, mas que o Wealth ainda mostra pendentes e não recebeu aviso."""
    resp = _respondidos(vault)
    corte = date.fromordinal(date.today().toordinal() - 30).isoformat()
    out = []
    for f in T._todas(vault):
        if not f['feito'] or (f['feita_em'] or '') < corte:
            continue
        pid, p = _passo_da_tarefa(f, plano)
        if p and p.get('status') != 'feito' and resp.get(pid) != 'feito':
            out.append({'passo': pid, 'acao': p.get('acao'), 'feita_em': f['feita_em'], 'inicio': p.get('inicio'), 'fim': p.get('fim')})
    return out


def avisar_wealth(vault, linha_txt, feito):
    """Chamado quando você marca/desmarca uma tarefa: se for do plano, avisa o Wealth (respostas.jsonl)."""
    f = T.ler_linha(linha_txt) or {}
    m = re.search(r'\bplano (p\d+)\b', f.get('fonte') or '')
    if not m:
        return None
    try:
        return mesa.responder(vault, {'tipo': 'plano', 'id': m.group(1), 'acao': 'feito' if feito else 'desfazer',
                                      'nota': 'marcado no Tarefas do Orbitus; a nota de corretagem vai para a pasta Entrada'})
    except ValueError:
        return None
