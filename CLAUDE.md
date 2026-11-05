# Orbitus — Manual do sistema

O Orbitus é o **painel central da vida do Marcio**: um cofre Obsidian que junta tarefas, agenda, e-mails,
treino e alimentação, viagens e o estado de todos os outros sistemas dele. Ao trabalhar aqui, você opera o hub,
não um assistente genérico.

## Princípios (aprovados em 2026-10-30; princípio 3 reescrito em 2026-11-04)

1. **Uso diário primeiro.** O Orbitus existe para ser aberto todo dia.
2. **Saúde visível.** Todo sistema e toda rotina aparecem no painel com 🟢/🟡/🔴. Rotina que parar fica vermelha
   no dia seguinte, nunca em silêncio (ver "Rotinas do Orbitus").
3. **Mudança entra por necessidade comprovada, não por data.** Toda mudança é classificada antes de ser feita:
   - **Correção** (algo quebrado ou escondido): entra direto.
   - **Acabamento** (melhora sem mudar a estrutura: texto, espaçamento, contraste, carregamento): entra com evidência.
   - **Estrutural** (aba, módulo, agente, redesenho visual): passa pelo portão abaixo e o Marcio aprova.
     Agente aprovado ganha lugar na sala 3D na mesma entrega, sem novo portão (ver "Sala dos agentes").

   Portão das mudanças estruturais (as quatro precisam ser "sim"):
   1. **Há uma dor com evidência?** Dado de uso (mapa de calor, tempo na aba, clique sem efeito), falha do Pulso,
      ou um "tentei fazer X e não consegui" do Marcio. "Ficaria bonito" ou "seria legal ter" não conta.
   2. **O sistema está estável?** Com 🔴 aberto no painel, só entram correções.
   3. **Não cabe no que já existe?** Primeiro melhorar a tela ou o agente atual; coisa nova só se a dor não couber.
   4. **É a única mudança grande em andamento?** A próxima começa quando a anterior foi usada e conferida.

   Registro e conferência: cada mudança estrutural vira uma linha em `00_Sistema/mudancas.md` (dor, evidência,
   decisão). Sete dias depois o Lente confere no uso se a dor diminuiu; se não diminuiu, a mudança é revista ou desfeita.
   Quem avalia: Lente (uso), Pulso (estabilidade), Marcio (decide).

## Estrutura

| Pasta | O que é |
|---|---|
| `Home.md` | painel no Obsidian (o painel principal é o app) |
| `00_Sistema/` | regras, `sistemas.json`, `marcos.json`, `concierge.json` (voz), `rotinas/` (sinais das rotinas) |
| `01_Federacao/` | gerado por `Scripts/coletar_federacao.py`, não editar à mão |
| `10_Tarefas/` | tarefas no formato do plugin Tasks (`- [ ] texto 📅 AAAA-MM-DD ⏫`) |
| `20_Email/` | resumo das caixas |
| `20_Treino/` | Shape Dezembro: `dias/AAAA-MM-DD.json` (um por dia), `despensa.json`, `locais.json`, `resumo.json`, `Mesa da Saúde/` |
| `30_Viagens/<viagem>/` | `roteiro.json`, `Lista.md`, `Documentos/` (uma pasta por viagem) |
| `90_Ideias/` | ideias soltas |
| `App/` | o painel (servidor Python + `static/`) |
| `Scripts/` | `coletar_federacao.py`, `backup_orbitus.py` |

## Federação

- Cada sistema é soberano e mora na própria pasta em `~/System/`. O Orbitus nunca edita arquivos de outro
  sistema, exceto o `_orbitus/INBOX.md` dele e o `respostas.jsonl` da Mesa do Wealth (só acrescenta).
- Cada sistema escreve `_orbitus/STATUS.md` e `_orbitus/MENSAGEM.md`. Regras em [[Protocolo de Federação]].
- **Três camadas (2026-11-02):** dados e regras ficam com o sistema; a operação dos agentes é do Orbitus; mudanças aprovadas pelo Marcio o Orbitus executa (etapa 3). Inventário em [[Inventário de Agentes]].

## App (painel visual)

App local em `App/` (Python, só biblioteca padrão), em http://localhost:8787, serviço do launchd `com.orbitus.app`
(`App/instalar.sh`). Reiniciar: `launchctl kickstart -k gui/$(id -u)/com.orbitus.app`. Abas: Home, Tarefas,
Treino (com Mesa da Saúde), Wealth (com a Mesa de investimentos), Agenda, E-mails, Viagem. Detalhes em `App/LEIA-ME.md`.

## Agentes e rotinas (tarefas agendadas do Claude; exigem o Mac ligado e o app do Claude aberto)

| Horário | Rotina | Rastro no cofre |
|---|---|---|
| 07:47 | Radar da bagagem GOL (volta 26/12) | `30_Viagens/Praia do Forte 2026/roteiro.json` › `bagagem.radar` |
| 10:37 e 22:37 | Sentinela das rotinas do Wealth (confere, tenta de novo uma vez, avisa) | `00_Sistema/rotinas/sentinela_wealth.json` |
| 13:37 e 20:37 | Lembrete de treino e alimentação (push) | `00_Sistema/rotinas/lembretes.json` |
| 21:47 | Mesa da Saúde: parecer do Personal e da Nutricionista | `20_Treino/Mesa da Saúde/pareceres/AAAA-MM-DD.json` |
| qua 09:23 | Lente: avaliação semanal de UX/UI (`00_Sistema/agentes/lente.md`) | `00_Sistema/rotinas/lente.json` · avaliações em `00_Sistema/lente/` |
| 23:17 | Backup do cofre (launchd `com.orbitus.backup`, não é tarefa do Claude) | `00_Sistema/rotinas/backup.json` |

O painel mostra tudo isso como o sistema "Rotinas do Orbitus".

## Sala dos agentes (Home)

O centro da Home é a sala 3D (`App/static/rosto/sala3d.js`, three.js). Personagens: Vega (concierge, mesa), CIO (cofre do Wealth), Brasa (personal) e Sálvia (nutricionista) no raio-x, Pulso (saúde do sistema) no rack, Lente (UX/UI) com a lupa e o cavalete que mostra o mapa de calor do dia (`/api/uso?resumo=1`, entrou em 2026-11-04 a pedido do Marcio). Cada boneco mostra um dado real de `/api/dados` e `/api/sistema`; sem valores em reais. **A sala é o mostruário do Orbitus**: o Marcio a usa para apresentar e vender o sistema a empresas e pessoas.
Por isso, **todo agente ativo precisa estar na sala**, entregue junto com o agente (decisão de 2026-11-04). Para cada agente novo:
personagem com cor e objeto próprios ligados à função; etiqueta "Nome · Função" com um dado real (sem dado ainda,
mostra o estado: "em teste desde DD/MM"); posição que não cubra outro personagem nem a legenda central; conferir no
Chrome antes de entregar, nos dois modos (real e `?demo=1`). Agente desligado sai da sala. `?anel=1` volta ao anel 2D.

## Modo de demonstração (mostruário)

Para apresentar o Orbitus a clientes: abrir `http://localhost:8787/?demo=1` (vale para a aba até `?demo=0`, ou o
link "sair" no selo do topo). `App/static/demo.js` intercepta todas as leituras de `/api/` e devolve dados fictícios
(pessoa "Ana", datas relativas a hoje); bloqueia toda gravação; a Vega responde com falas prontas, sem chamar a API;
a coleta de uso fica desligada. A vitrine é a Home com a sala; as outras abas mostram um aviso no lugar dos dados.
**Agente novo entra também no demo.js** (o dado fictício da etiqueta dele), senão aparece vazio na vitrine.

## Uso e mapa de calor (Lente)

`App/static/uso.js` (carregado no painel e no treino) grava cliques, troca de aba e tempo em cada aba em
`00_Sistema/uso/AAAA-MM.jsonl` via POST `/api/uso`. Só posição, elemento (tag/id/classe) e aba: **nunca texto**.
Mapa de calor por cima da tela real: abrir `http://localhost:8787/?calor=1` (amarelo = clique útil, rosa = clique
em algo que não faz nada). Quem lê: o Lente (UX/UI), toda quarta. Cada proposta dele vem classificada pelo princípio 3.

## Concierge (Vega)

A voz do Orbitus se chama Vega (nome na Home e no prompt `SISTEMA` de `concierge.py`; código e rotas continuam "concierge"). Personalidade: sagaz, com opinião baseada nos dados, ironia dosada, sem linguagem de atendimento. Rituais aceitam "bom dia, Vega".
Barra na Home (texto e voz). Usa a API do Claude com a chave no Keychain (`orbitus-anthropic`), teto mensal em
`~/.orbitus/concierge_uso.json`. Voz: Google Chirp 3 HD (chave `orbitus-google-tts`), escolhida em
`00_Sistema/concierge.json`; sem chave, usa a voz do Mac. Frases prontas: Bom dia, Boa tarde, Boa noite, Boa sexta.
Só consulta; a única ação permitida é criar tarefa.

## Convenções

Português. Datas AAAA-MM-DD. Wikilinks. Valores financeiros só no Wealth, nunca em STATUS/MENSAGEM.
**Credenciais nunca no cofre** (Keychain do Mac ou `~/.orbitus/`). O cofre vai para um GitHub privado todo dia.
