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
