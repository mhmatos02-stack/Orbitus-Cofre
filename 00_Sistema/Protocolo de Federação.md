# Protocolo de Federação (v2 · 2026-10-30)

Reconstrução do protocolo de 2026-07-22, perdido junto com o cofre original do Orbitus.

## Contrato de cada sistema federado

Na raiz do sistema, uma pasta `_orbitus/` com:

| Arquivo | Quem escreve | Conteúdo |
|---|---|---|
| `STATUS.md` | o sistema | linhas `**Data-base:**`, `**Saúde:**` (verde/amarelo/vermelho), `**Próxima ação:**`, `**Decisões que precisam do usuário:**`, `**Risco:**`. Máx. ~15 linhas |
| `MENSAGEM.md` | o sistema | recado curto em 1ª pessoa, com linha `**Esperando de você:**` quando houver |
| `INBOX.md` | o Orbitus | despachos `D-<SIGLA>-NNN`; o sistema marca `[processado em AAAA-MM-DD]` |

**Fronteira:** STATUS e MENSAGEM nunca levam valores, posições, transações ou credenciais.

## Regra de frescor

| Idade do STATUS | Painel |
|---|---|
| até 8 dias | cor declarada pelo sistema |
| 9 a 15 dias | 🟡 no mínimo ("sem sinal recente") |
| mais de 15 dias | 🔴 ("parado") |

Se o sistema tiver `00_System/Automation Status.md`, a linha `**Resultado:**` dele também entra no painel.

## Mesa de Decisões do AI Wealth Office (2026-10-30)

O Wealth Office publica a Mesa em `_orbitus/mesa/*.json` (decisões, lançamentos, atualizações, entregas, plano).
O Orbitus mostra a Mesa na aba própria e **só acrescenta** linhas em `_orbitus/mesa/respostas.jsonl`
(uma resposta do investidor por linha, com trava compartilhada). Quem aplica as respostas é a rotina das 20h47
do Wealth Office, via `Scripts/mesa_arquivos.py`. Valores aparecem na Mesa porque ela fica no Mac local;
STATUS e MENSAGEM seguem sem valores.
