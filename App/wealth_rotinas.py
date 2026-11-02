# -*- coding: utf-8 -*-
"""Orbitus — rotinas automáticas do AI Wealth Office no dia: rodou (verde), rodou com ressalva (amarelo),
falhou ou não rodou no horário (vermelho, com o motivo que dá para saber), ou ainda vai rodar.

Lê só o histórico que o próprio Wealth grava: <Wealth>/00_System/.automation_state/history.jsonl.
Somente leitura. Cadências conforme 00_System/Automation Registry.md do Wealth.
"""
import json, os
from datetime import date, datetime, timedelta

# agent_id, nome, quando roda (diario | uteis | dom | qui | dia1), hora, executor
ROTINAS = [
    ('health-check-wealth-office', 'Health Check', 'diario', '06:55', 'mac'),
    ('news-radar-wealth-office', 'News Radar', 'uteis', '07:45', 'claude'),
    ('monthly-report-wealth-office', 'Relatório mensal', 'dia1', '07:53', 'claude'),
    ('tesouro-wealth-office', 'Grade Tesouro', 'qui', '08:49', 'claude'),
    ('dashboard', 'Painel e sentinela', 'uteis', '10:05', 'mac'),
    ('cio-weekly-1on1-wealth-office', '1:1 do CIO', 'dom', '17:52', 'claude'),
    ('mesa-caixa-wealth-office', 'Mesa e caixa de entrada', 'diario', '20:47', 'claude'),
    ('git-commit-wealth-office', 'Backup do Wealth', 'diario', '23:00', 'mac'),
]
TOLERANCIA = 90          # minutos depois do horário antes de considerar "não rodou"


def _toca_hoje(regra, d):
    wd = d.weekday()
    return {'diario': True, 'uteis': wd < 5, 'dom': wd == 6, 'qui': wd == 3, 'dia1': d.day == 1}.get(regra, False)


def _local(iso):
    try:
        t = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    except ValueError:
        return None
    if t.tzinfo:
        t = t.astimezone().replace(tzinfo=None)
    return t


def status_automacao(wealth_dir):
    """Lê 00_System/Automation Status.md (gerado pelo Health Check do Wealth): resultado e as linhas que não estão verdes."""
    import re
    p = os.path.join(wealth_dir, '00_System', 'Automation Status.md')
    try:
        with open(p, encoding='utf-8') as f:
            t = f.read()
    except OSError:
        return None
    m = re.search(r'Atualizado em `([^`]+)`', t)
    r = re.search(r'\*\*Resultado:\*\*\s*(.+)', t)
    itens = []
    for l in t.split('## Recorrência')[0].splitlines():
        c = [x.strip() for x in l.strip().strip('|').split('|')]
        if len(c) >= 3 and (c[0].startswith('🟡') or c[0].startswith('🔴')):
            itens.append({'estado': 'falha' if c[0].startswith('🔴') else 'atencao', 'nome': c[1], 'evidencia': c[2]})
    return {'atualizado': (m.group(1)[:16].replace('T', ' ') if m else ''), 'resultado': (r.group(1).strip() if r else ''), 'itens': itens}


def historico(wealth_dir, desde):
    p = os.path.join(wealth_dir, '00_System', '.automation_state', 'history.jsonl')
    out = {}
    try:
        with open(p, encoding='utf-8') as f:
            for l in f:
                try:
                    j = json.loads(l)
                except ValueError:
                    continue
                t = _local(j.get('finished_at'))
                if not t or t.date() < desde:
                    continue
                out.setdefault(j.get('agent_id'), []).append((t, j))
    except OSError:
        return None
    return out


def do_dia(wealth_dir, d=None, agora=None):
    d = d or date.today()
    agora = agora or datetime.now()
    h = historico(wealth_dir, d)
    if h is None:
        return {'ok': False, 'erro': 'não achei o histórico de rotinas do Wealth', 'itens': []}
    itens = []
    for aid, nome, regra, hora, exe in ROTINAS:
        runs = sorted(h.get(aid, []), key=lambda x: x[0])
        runs = [r for r in runs if r[0].date() == d]
        if not _toca_hoje(regra, d) and not runs:
            continue
        it = {'id': aid, 'nome': nome, 'hora': hora, 'executor': exe}
        if runs:
            # o melhor resultado do dia vale (um 2º disparo "pulado" não apaga o sucesso das 8h)
            ordem = {'success': 0, 'skipped': 1, 'partial': 2}
            t, j = min(runs, key=lambda r: (ordem.get(r[1].get('status'), 3), -r[0].timestamp()))
            st = j.get('status') or '?'
            nota = j.get('note') or j.get('erro') or j.get('error') or j.get('resultado') or ''
            res = str(j.get('resultado') or '').upper()
            if st in ('success', 'skipped') and res in ('FALHA', 'CRÍTICO', 'CRITICO'):
                it.update(estado='falha', texto='rodou às %s e achou %s falha(s) no Wealth: veja 00_System/Automation Status.md' % (t.strftime('%H:%M'), j.get('failures', '?')))
            elif st in ('success', 'skipped') and res.startswith('ATEN'):
                sa = status_automacao(wealth_dir) or {}
                qual = '; '.join('%s: %s' % (x['nome'], x['evidencia']) for x in sa.get('itens', []) if x['estado'] == 'atencao')[:180]
                it.update(estado='atencao', texto='rodou às %s · atenção: %s' % (t.strftime('%H:%M'), qual or '%s ponto(s)' % j.get('warnings', '?')))
            elif st in ('success', 'skipped'):
                it.update(estado='ok', texto='rodou às ' + t.strftime('%H:%M'))
            elif st == 'partial':
                it.update(estado='atencao', texto='rodou em parte às %s%s' % (t.strftime('%H:%M'), ': ' + str(nota)[:160] if nota else ''))
            else:
                it.update(estado='falha', texto='falhou às %s%s' % (t.strftime('%H:%M'), ': ' + str(nota)[:160] if nota else ' (sem motivo registrado)'))
        else:
            hh, mm = map(int, hora.split(':'))
            prazo = datetime.combine(d, datetime.min.time()) + timedelta(hours=hh, minutes=mm + TOLERANCIA)
            if d < agora.date() or agora > prazo:
                motivo = ('o agente automático do Mac não rodou: o Mac estava desligado ou dormindo nesse horário?' if exe == 'mac' else
                          'a tarefa agendada não deixou registro: costuma ser o app Claude fechado no Mac mini, o Mac dormindo, ou falha da própria tarefa')
                it.update(estado='falha', texto='não rodou às %s · %s' % (hora, motivo))
            else:
                it.update(estado='agendada', texto='roda às ' + hora)
        # texto curto para a Home; o detalhe técnico fica na página Saúde do sistema
        tx = it.get('texto', '')
        it['curto'] = {'ok': tx.split(' · ')[0], 'agendada': tx}.get(it.get('estado'), tx.split(':')[0].split(' · ')[0])
        if it.get('estado') == 'falha' and tx.startswith('falhou'):
            it['curto'] = tx.split(':')[0] if ':' in tx[10:] else tx
            it['curto'] = 'falhou às ' + tx[10:15]
        elif it.get('estado') == 'falha' and tx.startswith('não rodou'):
            it['curto'] = tx.split(' · ')[0]
        elif it.get('estado') == 'falha':
            it['curto'] = 'achou falhas no Wealth'
        elif it.get('estado') == 'atencao':
            it['curto'] = tx.split(' · ')[0] + ' · com ressalva'
        itens.append(it)
    return {'ok': True, 'itens': itens,
            'falhas': sum(1 for x in itens if x['estado'] == 'falha'),
            'verdes': sum(1 for x in itens if x['estado'] == 'ok'),
            'atencao': sum(1 for x in itens if x['estado'] == 'atencao')}
