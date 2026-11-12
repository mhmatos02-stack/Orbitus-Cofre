# Registro de mudanças estruturais

Regra no princípio 3 do [[CLAUDE]]. Uma linha por mudança estrutural. O Lente preenche a coluna "conferido" 7 dias depois.

| Data | Mudança | Dor | Evidência | Portão (1·2·3·4) | Decisão | Conferido em 7 dias |
|---|---|---|---|---|---|---|
| 2026-11-04 | Coleta de uso e mapa de calor (`uso.js`, `?calor=1`) | Avaliar a interface sem dado de uso | Nenhum dado existia; pré-requisito do Lente | sim · 🟡 Wealth · sim · sim | Marcio aprovou | 2026-11-11: dor resolvida. 1.312 eventos em 7 dias, base da avaliação 02. Ajuste necessário: no celular o `pointerdown` conta rolagem como clique (52% mortos contra 9% no Mac) e a raiva marca água registrada em lote. Manter, com a correção proposta na avaliação 02. |
| 2026-11-04 | Lente na sala 3D | A sala é o mostruário comercial: agente ativo precisa aparecer | Regra do Marcio (04/11): todo agente ativo entra na sala | não se aplica (consequência de agente aprovado) | Marcio decidiu | 2026-11-11: sem dor medida. 27 toques na sala, todos sem efeito porque tocar num personagem não faz nada (proposta 4 da avaliação 02); nenhum padrão de toque indica personagem escondido. Legibilidade dos 6 não conferida na tela nesta rodada. Manter. |
| 2026-11-11 | Ponte Wealth → Tarefas: ordem com condição que o Wealth marca como "agora" (plano completo em `00_System/.automation_state/plano.json`) vira tarefa com "confira a condição"; "proximo"/"futuro" seguem na fila (`wealth_plano.liberacao`) | Ordens do Wealth não chegavam ao Tarefas: a trava de 09/11 esperava o campo `liberada`, que o Wealth nunca gravou (D-AIW-008) | WRLD11 p08 arquivada às 00:01 de 11/11 com o Wealth marcando "agora"; só 3 ordens sem condição chegavam | não se aplica (correção de defeito) | Marcio aprovou (11/11), com aviso no título | |
