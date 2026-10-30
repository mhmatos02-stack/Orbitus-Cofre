# Mesa da Saúde

Agentes que acompanham treino, alimentação e corpo do Marcio. Fonte de dados: `20_Treino/dias/*.json` (um registro por dia), `20_Treino/resumo.json`, `20_Treino/locais.json` e o plano Shape Dezembro (aba Treino do Orbitus).

## Como funciona
- Cada agente tem um arquivo em `agentes/`. O cabeçalho (frontmatter) é o que o Orbitus mostra; o corpo é a instrução do agente.
- Todo dia às 21:47 a rotina "Mesa da Saúde" lê os últimos 7 dias, as perguntas abertas e os locais de treino, e grava `pareceres/AAAA-MM-DD.json`.
- Perguntas feitas na aba Treino › Mesa entram em `perguntas.jsonl` e são respondidas na rotina seguinte.
- O Personal pode marcar onde o Marcio vai treinar em `locais.json` (casa, academia). O Orbitus troca o treino do dia sozinho.

## Formato do parecer (pareceres/AAAA-MM-DD.json)
```json
{"data":"AAAA-MM-DD","gerado_em":"AAAA-MM-DDTHH:MM","agentes":{
  "personal":{"resumo":"...","bem":["..."],"ajustes":["..."],"amanha":"...","alerta":""},
  "nutri":{"resumo":"...","bem":["..."],"ajustes":["..."],"trocas":[{"de":"...","por":"...","porque":"..."}],"amanha":"...","alerta":""}},
 "respostas":[{"id":"<id da pergunta>","agente":"personal|nutri","texto":"..."}],
 "semana":"(só aos domingos) leitura da semana: cintura, peso, aderência, decisão da regra de ajuste"}
```

## Regras da mesa
- Nada de diagnóstico, remédio ou suplemento além de creatina e whey, que já estão no plano. Dor, tontura ou lesão: parar e procurar um profissional.
- Nunca recomendar menos de 1.650 kcal por dia nem jejum longo, diurético ou dieta de choque.
- Ser direto e específico: números, alimentos e exercícios concretos. Elogiar o que foi feito de verdade, sem bajular.
- Para criar uma cadeira nova, copie um arquivo de `agentes/`, troque o cabeçalho e o texto, e ponha `status: ativo`.
