# App do Orbitus

O painel visual do Orbitus. O cofre Obsidian é a base de dados: o app lê e grava arquivos dele.

- **Abrir:** http://localhost:8787. Serviço do launchd, sobe sozinho no login.
- **Instalar ou atualizar:** `bash ~/System/Orbitus/App/instalar.sh`
- **Reiniciar depois de mudar um .py:** `launchctl kickstart -k gui/$(id -u)/com.orbitus.app`
- **Log:** `~/.orbitus/app.log` · backup: `~/.orbitus/backup.log`
- **Backup diário (23:17):** `bash ~/System/Orbitus/App/instalar_backup.sh https://github.com/<conta>/Orbitus.git`

## Arquivos do app

| Arquivo | Faz |
|---|---|
| `server.py` | servidor, Home, tarefas, agenda, saúde das rotinas, contexto do Concierge |
| `emails.py` · `wealth.py` · `mesa.py` | e-mails (IMAP, só leitura), cockpit e Mesa do AI Wealth Office |
| `viagem.py` | viagens: roteiro, lista, documentos, checklist da véspera, radar de bagagem |
| `treino.py` | registros diários do treino, despensa, locais, resumo calculado, Mesa da Saúde |
| `concierge.py` | Concierge (API do Claude) e voz (Google Chirp 3 HD ou a do Mac) |
| `static/index.html` | todas as telas, menos o treino |
| `static/treino.html` | aba Treino (o antigo Shape Dezembro), aberta dentro do painel |

## De onde vem cada bloco

| Bloco | Fonte |
|---|---|
| Tarefas | `10_Tarefas/*.md`, plugin Tasks. Marcar no painel grava `[x] ✅ data` |
| Capturar (campo + Enter) | seção Inbox de `10_Tarefas/Tarefas.md` |
| Sistemas, sino, "Esperando de você" | `01_Federacao/` + "Rotinas do Orbitus" (sinais em `00_Sistema/rotinas/` e nos rastros de cada rotina) |
| Calendário | `~/.orbitus/agenda.txt` (links ICS); sem ele, `00_Sistema/agenda.json` |
| Contagem das viagens | `00_Sistema/marcos.json` |
| Treino | `20_Treino/` (ver CLAUDE.md) |
| Viagem | `30_Viagens/<viagem>/` |
| Wealth e Mesa | `~/System/AI Wealth Office/` (cockpit e `_orbitus/mesa/`) |

## Convenções de tarefa

`- [ ] Título — contexto 🔺 📅 2026-11-05 #financas`
Tudo depois de ` — ` vira a linha cinza. Prioridade: 🔺 máxima · ⏫ alta · 🔼 média · 🔽 baixa.
`#financas` (ou `#wealth`) vira Finanças; o resto é Pessoal. Na Home aparece só a semana (até domingo).

## Segurança

- Escuta só em 127.0.0.1. Gravações com Origin conferida e só nas pastas de cada módulo.
- Segredos fora do cofre: Keychain (`orbitus-email`, `orbitus-anthropic`, `orbitus-google-tts`) e `~/.orbitus/`
  (links ICS, uso do Concierge). O cofre vai para um GitHub **privado**; nunca ponha credencial dentro dele.
- O Concierge manda um retrato do painel para a API do Claude a cada pergunta e só pode criar tarefas.

## Acesso pelo celular (Tailscale)
- Endereço: https://mac-mini.taila77abf.ts.net (só aparelhos da sua rede Tailscale; Funnel desligado)
- Publicação: `/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg 8787` (fica salvo; desligar com `serve --https=443 off`)
- Abrir no login: `bash ~/System/Orbitus/App/instalar_tailscale_login.sh` (agente com.orbitus.tailscale, reabre a cada 10 min)
- Chave do mac-mini: expiração desligada no painel da Tailscale

## Concierge (atualização P1, 30/10)
- Resposta em streaming: POST /api/concierge/fluxo (server-sent events). A voz começa na primeira frase; o resto é sintetizado em blocos de ~2 frases e tocado em sequência.
- Contexto por assunto: concierge.intencoes() escolhe finanças, treino, viagem, e-mails, agenda ou tarefas; rituais e perguntas abertas mandam tudo. O rodapé da resposta mostra os tokens e o recorte usado.
- Fala: concierge.para_fala() ajusta só o texto falado (Márcio, siglas, datas por extenso, unidades, sem emojis ou markdown).
- Microfone: segurar = fala e envia ao soltar; toque rápido = mãos livres; no Mac, segurar ⌥ espaço; Esc interrompe; tocar na resposta corta a voz.

## Passos do Apple Saúde (Atalho do iPhone)
- POST https://mac-mini.taila77abf.ts.net/api/treino/saude com JSON {"passos": N} (opcional "data": "AAAA-MM-DD"). Grava steps no dia, sem apagar o resto.
- Automação no Atalhos: 20:15 e 23:45, todos os dias, executar sem perguntar. Precisa do Tailscale ligado no iPhone.

## Lista do dia (31/10)
- Embaixo do calendário da Home: rotina + tarefas com data + agenda, em ordem de horário, com check. Segue o dia selecionado no calendário.
- Rotina que se repete: 10_Tarefas/Rotina diária.md (`- HH:MM Texto [dias]`). Feitos: 10_Tarefas/Rotina/AAAA-MM.json.
- Coisa de um dia só: tarefa normal com `📅 AAAA-MM-DD ⏰ HH:MM` (ou o campo "+ adicionar" embaixo da lista).
- Treino, ioga, pilates, corrida e copos de água se marcam sozinhos pelo registro da aba Treino.
- API: GET /api/dia?d=AAAA-MM-DD · POST /api/dia/marcar · POST /api/dia/adicionar. O Concierge recebe a lista_do_dia e o "Bom dia" lê em ordem.

## Tarefas (31/10)
- Aba Tarefas: criar (linguagem natural: "sexta 10h", "amanhã", "todo dia", "toda segunda", "urgente", "#trabalho"), situação (a fazer · fazendo · aguardando), editar, remover com desfazer, Concluídas (30 dias), Arquivo e Sugeridas.
- Áreas por tag: #pessoal #trabalho #financas #saude #viagem. Situação por tag: #fazendo #aguardando. Repetição no formato do plugin Tasks (🔁 every week on Monday); ao concluir no painel, a próxima entra logo acima.
- Remover = vira "- [-] … 🗑 data" na seção "## Arquivo" do Tarefas.md. Restaurar devolve para a Inbox.
- Sugestões: Mesa do Wealth (plano e decisões), e-mails que pedem resposta, alertas de viagem, falhas das rotinas e tarefas do parecer da Mesa da Saúde. Aceitas/dispensadas em 00_Sistema/tarefas_sugestoes.json.
- Siri e Compartilhar: POST https://mac-mini.taila77abf.ts.net/api/tarefas/rapida {"texto": "...", "url": "..."} → devolve "falar" para a Siri ler.

## Lista do dia ↔ Treino, água e avisos (31/10)
- Marcar treino, ioga, pilates ou corrida na lista do dia grava na aba Treino (workout.done/yoga/pilates/corrida) e pontua. Ioga passou a pontuar em qualquer dia (+15 XP).
- Água: a linha `- água: 10 copos de 250 ml, das 08:00 às 20:00` da Rotina diária vira 5 lembretes (2 copos cada). Marcar soma no contador de água do Treino; desmarcar tira. Se você registrar a água no Treino, os lembretes se marcam sozinhos.
- Avisos (Web Push): `bash ~/System/Orbitus/App/instalar_push.sh` instala o pywebpush, cria as chaves em ~/.orbitus e reinicia. No iPhone, abrir pelo ícone da Tela de Início e tocar em "Ativar avisos" embaixo da lista do dia. Avisa água e tarefas com ⏰ na hora (até 10 min de atraso), com o Mac ligado.
- (31/10, revisão) Água saiu da lista do dia: virou um contador único embaixo do "Hoje" (barra, ritmo esperado, + copo / −). O aviso de água só sai se você estiver atrás do ritmo naquele horário. O Concierge comenta a hidratação nos rituais e, fora deles, só se estiver 2+ copos atrás; quando você diz "bebi meio litro", ele soma ([[agua: N]]).
- Itens feitos somem da lista do dia (com Desfazer); "✓ N feitos · mostrar" traz de volta.

## Agenda proativa (31/10)
- Aba Agenda (#agenda), módulo App/agenda_pro.py, GET /api/agenda?dias=45. Somente leitura.
- Junta: compromissos (ICS), tarefas com data, viagens (voos/estadias), proventos previstos e agenda do Wealth, feriados (BR, SP; DE-BW e CH-Berna nos dias da viagem) e datas do comércio (Black Friday, Mães, Pais…).
- Clima: Open-Meteo (grátis, sem chave), 16 dias, no local onde você estará (roteiros das viagens; senão São Paulo). Além de 16 dias, usa a média do roteiro. Cache de 3 h.
- Levar: regras por palavra (festa → presente; voo → documento e cartão de embarque; academia → roupa de treino; reunião → notebook…) + clima (chuva → guarda-chuva; frio → casaco) + a lista "levar" da parada da viagem.
- Radar: presente que falta, chuva em dia de saída, dia cheio, horários colados, feriado que fecha banco/B3, proventos dos próximos 10 dias, Black Friday, Natal e Ano-Novo (onde você estará).
- O Concierge recebe o radar e os próximos 10 dias quando a pergunta é de agenda/viagem e nos rituais.

## Conversa com o CIO (31/10)
- Na Mesa (#mesa): botão "Falar com o CIO" e o painel de conversa. Módulo App/cio.py, POST /api/cio (streaming), /api/cio/nova, /api/cio/1on1.
- O CIO lê: SKILLS/Chief Investment Officer (CIO).md, IPS, Constraints, última Mesa (contexto + final da ata), último 1:1, Decision Journal recente, pendências da Mesa e a foto da carteira. O bloco de documentos vai em cache na API (perguntas seguidas em até 5 min saem bem mais baratas). Gasto soma no mesmo teto do Concierge.
- Escritas: a conversa fica em Orbitus/01_Federacao/Conversas com o CIO/AAAA-MM-DD.md; "Levar ao 1:1" acrescenta um despacho D-AIW-NNN no _orbitus/INBOX.md do Wealth (Protocolo de Federação), que o 1:1 de domingo processa. Nada vira decisão formal sem a Mesa e o Decision Journal; nunca executa ordens.
