# Inventário de Agentes e Sistemas (etapa 1 · 2026-11-02)

Levantamento feito pelo Orbitus, só leitura. Nada foi alterado nos sistemas. Base para a etapa 2
(registro central + Sentinela ampliada). Modelo de governança: [[Protocolo de Federação]] › "Três camadas".

## Sistemas

| Sistema | Pasta | Última mudança | Federado (`_orbitus/`) | Proposta | Observação |
|---|---|---|---|---|---|
| Orbitus | `~/System/Orbitus` | 2026-11-02 | (é o hub) | **ativo** | |
| AI Wealth Office | `~/System/AI Wealth Office` | 2026-11-02 | sim | **ativo** | 12 agentes |
| Investimentos IA | `~/Documents/Systems/Investimentos IA` | 2026-10-30 | não | **absorver no Wealth** (D-AIW-007) | planilha e dashboard financeiro fora do Wealth: sobrepõe o Wealth e fura a regra "valores só no Wealth" |
| Orchestr-io | `~/Documents/Systems/Orchestr-io` | 2026-10-29 | não | **não é sistema** | 1 arquivo (ideia do conselho); vira nota em `90_Ideias/` ou fica onde está |
| Livro | `~/Documents/Systems/Livro` | 2026-10-02 | não | **ativo** (decisão 02/11) | 31 dias parado |
| Professional_Growth_OS | `_arquivados/` | 2026-09-25 | não | **arquivado 02/11** | 38 dias parado |
| Desenvolvedor-Prompts-Senior | `_arquivados/` | 2026-08-10 | não | **arquivado 02/11** | 84 dias parado |
| Marketing_OS_Obsidian | `_arquivados/` | 2026-07-23 | sim | **arquivado 02/11** | 102 dias parado; `STATUS.md` ilegível ("Resource deadlock avoided", iCloud) |
| Obra Banheiro | `_arquivados/` | 2026-07-24 | sim | **arquivado 02/11** | 101 dias parado; obra concluída? |
| Agentic-OS | `~/Documents/Systems/Agentic-OS` | 2026-07-07 | não | **ativo** (decisão 02/11) | 118 dias parado |

## Agentes

### Orbitus (7)
| Agente | Tipo | Horário | Rastro | Monitorado? |
|---|---|---|---|---|
| Radar bagagem GOL | tarefa agendada `trig_01Bztv5zd8KatDiCpGDN63M9` | 07:47 | `roteiro.json › bagagem.radar` | sim |
| Lembrete treino e alimentação | tarefa agendada `trig_01X49W5i4vrv4DJEMCKiBcNA` | 13:37, 20:37 | `rotinas/lembretes.json` | sim |
| Mesa da Saúde | tarefa agendada `trig_01FMUVFYiMDpn6D71UAeXwW8` | 21:47 | `Mesa da Saúde/pareceres/` | sim |
| Sentinela das rotinas do Wealth | tarefa agendada `trig_015UCipc8iqfisz4Ty55dtTT` | 10:37, 22:37 | `rotinas/sentinela_wealth.json` | sim (desde 02/11) |
| Lente (UX/UI) | tarefa agendada (a criar) | qua 09:23 | `rotinas/lente.json` · `00_Sistema/lente/` | sim (a partir de 11/11) |
| App (painel) | launchd `com.orbitus.app` | sempre (KeepAlive) | `reinicio.log` | não |
| Backup do cofre | launchd `com.orbitus.backup` | 23:17 | `rotinas/backup.json` | sim |
| Tailscale login | launchd `com.orbitus.tailscale` | (no login) | `~/.orbitus/` | não |

### AI Wealth Office (12)
| Agente | Tipo | Horário | Sentinela confere? |
|---|---|---|---|
| News Radar | tarefa agendada `trig_01QUK3u8wrTMpkbJS5cFUe3Y` | seg-sex 07:45 | sim |
| Mesa e caixa de entrada | tarefa agendada `trig_01HrJ6HVEKWsFxt5CeFCQ5Xh` | 20:47 | sim |
| 1:1 do CIO | tarefa agendada `trig_01Pb9hgVCGwPV7axC1W5KJE4` | dom 17:52 | sim |
| Fechamento mensal | tarefa agendada `trig_016Ys3FYhCkYL5rBnWRBZtLV` | dia 1, 07:53 | sim |
| Grade Tesouro | tarefa agendada `trig_01PvmtYmkeq8QCyLbnCM1zvf` | qui 08:49 | sim |
| Revisão anual | tarefa agendada `trig_01QXkoBiCLLixBe6hkVmyisc` | 02/01 07:51 | não |
| Preparação DIRPF | tarefa agendada `trig_01VvpXDtseAD1iFhN3pZdU1t` | 05/03 08:50 | não |
| Health Check | launchd `com.wealthoffice.healthcheck` | 06:55 + login | sim |
| Dashboard + sentinela | launchd `com.wealthoffice.dashboard` | seg-sex 10:05, 14:05, 18:05 | sim (só a das 10:05) |
| Sentinela de eventos | launchd `com.wealthoffice.eventos` | seg-sex a cada 15 min, 9h-19h | **não** |
| Commit diário (backup) | launchd `com.wealthoffice.backup` | 23:00 + login | sim |
| Teste de restauração | launchd `com.wealthoffice.restore` | dia 3, 07:10 | **não** |

### Fora destas pastas (1)
| Agente | Estado | Observação |
|---|---|---|
| Atualizar ViK OS (Grupo Vik) | **desligado desde 12/10** | aponta para `/Users/marciohpmatos/...`, outro usuário/computador. Não é deste ecossistema: apagar ou religar, não deixar esquecido |

Nos outros 8 sistemas não foi achado nenhum agente agendado (busca por launchd/cron e nas tarefas agendadas). Leitura parcial em `Documents/Systems` por bloqueio do iCloud.

## Lacunas achadas

1. **Sentinela de eventos e teste de restauração do Wealth não são conferidos por ninguém.** O teste de restauração estreia amanhã (03/11, 07:10).
2. **`Documents/Systems` está sujeito a deadlock do iCloud** (mesmo problema que o Wealth resolveu em set/2026 saindo de lá). O Orbitus não consegue gerir de forma confiável o que não consegue ler. Sistemas que ficarem ativos devem ir para `~/System/`.
3. **Duas fontes de dados financeiros** (Wealth e Investimentos IA).
4. **Nenhum agente tem dono registrado em lugar nenhum além do próprio agendador.** É isso que a etapa 2 resolve.

## Decisões (02/11)
- Arquivados em `Documents/Systems/_arquivados/`: Desenvolvedor-Prompts-Senior, Professional_Growth_OS, Marketing_OS_Obsidian, Obra Banheiro.
- Ativos: Orbitus, AI Wealth Office, Livro, Agentic-OS. Orchestr-io é nota, não sistema.
- Investimentos IA: absorver no Wealth (despacho D-AIW-007); arquivar depois que o Wealth confirmar.
- ViK OS: fica como está, registrado como fora do ecossistema.
