/* Orbitus · modo de demonstração (mostruário para clientes).
   Ligar: abrir o painel com ?demo=1 (vale para a aba até ?demo=0). Com ele ligado:
   - toda leitura do servidor (/api/...) recebe dados FICTÍCIOS daqui; nada real chega à tela;
   - toda gravação é bloqueada (nada muda no cofre); a Vega responde com falas prontas, sem chamar a API;
   - a coleta de uso (uso.js) fica desligada;
   - abas fora da vitrine (Wealth, Treino, E-mails, Viagem, Agenda, Mesa) mostram um aviso no lugar dos dados. */
(function () {
  var q = location.search;
  try {
    if (/[?&]demo=1/.test(q)) sessionStorage.setItem('orbitus.demo', '1');
    if (/[?&]demo=0/.test(q)) sessionStorage.removeItem('orbitus.demo');
  } catch (e) {}
  var ligado = false;
  try { ligado = sessionStorage.getItem('orbitus.demo') === '1'; } catch (e) { ligado = /[?&]demo=1/.test(q); }
  window.ORBITUS_DEMO = ligado;
  if (!ligado) return;

  var NOME = 'Ana';
  var agora = new Date();
  function iso(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  function mais(n) { var d = new Date(agora); d.setDate(d.getDate() + n); return iso(d); }
  function hm(d) { return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); }
  function haMin(n) { var d = new Date(agora.getTime() - n * 60000); return iso(d) + 'T' + hm(d); }
  var HOJE = iso(agora);

  /* ---------- tarefas ---------- */
  var TF = [
    ['Enviar a proposta revisada para a Lumen Arquitetura', 'Trabalho', 1, 3, '', ''],
    ['Preparar a pauta da reunião de sócios', 'Trabalho', 1, 2, '10:00', ''],
    ['Renovar o seguro do carro', 'Pessoal', 2, 2, '', ''],
    ['Revisar o aporte mensal da carteira', 'Finanças', 3, 2, '', 'sugerido pela Mesa de Finanças'],
    ['Comprar o presente de aniversário da Clara', 'Pessoal', 3, 1, '', ''],
    ['Marcar o check-up anual', 'Saúde', 4, 1, '', 'sugerido pela Mesa da Saúde'],
    ['Ler o capítulo 4 do livro do clube', 'Pessoal', 5, 0, '', ''],
    ['Reservar o hotel em Lisboa', 'Viagem', 6, 1, '', '']
  ];
  var TAREFAS = TF.map(function (t, i) {
    return { arquivo: '10_Tarefas/Tarefas.md', linha: 10 + i, texto: '- [ ] ' + t[0], titulo: t[0], fonte: t[5], hora: t[4], status: '', repete: '', url: '',
      criada: mais(-2), tag: t[1], due: mais(t[2]), prio: t[3], feito: false, col: 'semana', atrasada: false };
  });

  /* ---------- agenda (relativa a hoje) ---------- */
  var EV = {};
  function ev(n, h, t, c) { (EV[mais(n)] = EV[mais(n)] || []).push([h, t, c || 'b']); }
  ev(0, '10:00', 'Reunião com a equipe de produto'); ev(0, '15:30', 'Call com a Studio Norte');
  ev(1, '09:00', 'Dentista', 'r'); ev(2, '14:00', 'Apresentação para a Lumen');
  ev(3, '19:30', 'Jantar com amigos'); ev(5, 'dia todo', 'Aniversário da Clara', 'r');
  ev(8, '08:00', 'Corrida no parque'); ev(12, '11:00', 'Reunião de sócios'); ev(24, 'dia todo', 'Viagem: Lisboa', 'r');

  /* ---------- dia (lista com horário) ---------- */
  function dia(d) {
    var hojeSim = d === HOJE, passou = function (h) { return hojeSim && h < hm(agora); };
    var r = [['07:30', 'Meditação de 10 minutos', null], ['09:00', 'Fazer o treino do dia', 'treino'], ['12:30', 'Almoço longe da tela', null], ['21:30', 'Ler 20 páginas', null]];
    var itens = r.map(function (x, i) {
      var it = { tipo: 'rotina', id: 'demo-' + i, hora: x[0], texto: x[1], liga: x[2], feito: passou(x[0]) && i !== 1, auto: x[2] === 'treino', quando: null };
      if (x[2] === 'treino') it.detalhe = 'Pernas';
      return it;
    });
    (EV[d] || []).filter(function (e) { return e[0] !== 'dia todo'; }).forEach(function (e, i) {
      itens.push({ arquivo: '10_Tarefas/Tarefas.md', linha: 50 + i, linha_txt: '', hora: e[0], texto: e[1], feito: passou(e[0]), atrasada: false, due: d, tipo: 'tarefa' });
    });
    itens.sort(function (a, b) { return (a.hora || '99').localeCompare(b.hora || '99'); });
    var feitos = itens.filter(function (i) { return i.feito; }).length, beb = hojeSim ? 6 : 0;
    return { dia: d, itens: itens, arquivo: '10_Tarefas/Rotina diária.md', feitos: feitos, total: itens.length,
      agua: { bebidos: beb, meta: 10, ml: 250, esperado: 6, atras: 0, slots: [['08:00', 2, 2], ['11:00', 2, 4], ['14:00', 2, 6], ['17:00', 2, 8], ['20:00', 2, 10]], proximo: '' },
      wealth_rotinas: ROTINAS };
  }
  function rot(id, nome, hora, exe, estado, quando) {
    var t = estado === 'ok' ? 'rodou às ' + quando : 'roda às ' + hora;
    return { id: id, nome: nome, hora: hora, executor: exe, estado: estado, texto: t, curto: t };
  }
  var h = hm(agora);
  var ROTINAS = { ok: true, itens: [
    rot('health', 'Verificação diária', '06:55', 'mac', 'ok', '06:57'),
    rot('news', 'Radar de notícias', '07:45', 'claude', h > '07:50' ? 'ok' : 'agendada', '07:48'),
    rot('painel', 'Painel e sentinela', '10:05', 'mac', h > '10:10' ? 'ok' : 'agendada', '10:06'),
    rot('mesa', 'Mesa e caixa de entrada', '20:47', 'claude', h > '20:55' ? 'ok' : 'agendada', '20:49')
  ] };
  ROTINAS.verdes = ROTINAS.itens.filter(function (x) { return x.estado === 'ok'; }).length; ROTINAS.falhas = 0; ROTINAS.atencao = 0;

  /* ---------- painel principal ---------- */
  function dados() {
    return {
      hoje: HOJE, agora: hm(new Date()), tarefas: TAREFAS,
      federacao: [
        { tipo: 'federacao', id: 'financas', nome: 'Escritório Financeiro', icone: '💰', coletado: HOJE, saude: '🟢', motivo: '', idade: 0, data_base: HOJE,
          saude_txt: 'verde. Carteira e razão atualizados hoje.', proxima: 'Rebalanceamento trimestral em dezembro', decisoes: '', risco: '', esperando: '', esperando_lista: [],
          automacao: '🟢 0 falha(s)', falhas: [] },
        { id: 'orbitus', nome: 'Rotinas do Orbitus', icone: '🛰️', saude: '🟢', saude_txt: 'verde. Em dia: backup, lembretes, Mesa da Saúde, Lente.', falhas: [],
          esperando: '', esperando_lista: [], proxima: 'todos os dias às 07:45, 13:30, 20:30 e 23:15', automacao: '0 falha(s) · 0 atenção(ões)' }
      ],
      eventos: EV, agenda_fonte: 'ICS ao vivo', ocupados_proximo_mes: 6,
      marcos: [{ nome: 'Viagem: Lisboa', curto: 'Lisboa', data: mais(24), dias: 24 }, { nome: 'Meia maratona', curto: 'Meia maratona', data: mais(52), dias: 52 }],
      treino: { divisao: 'ABC', local: 'academia', ate: mais(60), equipamentos: [], sessoes: {} },
      treino_resumo: { data: HOJE, d12: Math.max(0, Math.round((new Date(agora.getFullYear(), 11, 12) - new Date(agora.getFullYear(), agora.getMonth(), agora.getDate())) / 864e5)), sessao: 'B', sessao_nome: 'Pernas', treino_ok: false, peso: 64.2, peso_media7: 64.4, peso_base: 66, cintura: 74, cintura_data: mais(-3),
        cintura_base: 77, cintura_meta: 72, passos_hoje: 6240, mov_hoje: 0, passos_media7: 7800, passos_meta: 9000, proteina: 82, proteina_meta: 120, kcal: 1240, kcal_meta: 1900,
        agua: 6, agua_meta: 10, treinos_semana: 3, treinos_alvo: 5, pontos: 3, sequencia: 4, xp: 1240, nivel: 3, nivel_nome: 'Em ritmo', calculado_em: HOJE + 'T' + hm(agora), semana: {} },
      emails: EMAILS,
      mesa_home: { disponivel: true, hoje: HOJE, respostas: {}, lancamentos_aguardando: 2,
        abertas: [{ id: 'demo-d1', titulo: 'Aumentar a reserva de emergência para 8 meses?', prazo: mais(3), status: 'aberta' }],
        proximos_passos: [{ id: 'demo-p1', acao: 'Aporte mensal na carteira de dividendos', inicio: mais(1), condicao: 'depois que o salário cair', status: 'pendente', quem: 'voce' },
          { id: 'demo-p2', acao: 'Rever a cobertura do seguro de vida', inicio: mais(4), condicao: '', status: 'pendente', quem: 'voce' }] },
      viagem_alertas: []
    };
  }
  function mail(i, conta, de, end, assunto, min, lido, pede, previa) {
    return { conta: conta, uid: String(i), de: de, email: end, assunto: assunto, quando: haMin(min), mid: 'demo-' + i + '@orbitus.demo', lido: lido, pessoa: true, pede: pede, previa: previa };
  }
  var TODOS = [
    mail(1, 'Gmail', 'Beatriz Lima', 'beatriz@lumen.demo', 'Proposta: conseguimos fechar até sexta?', 35, false, true, 'Oi, Ana! Revisei com o time e só falta alinhar o cronograma.'),
    mail(2, 'iCloud', 'Rafael Costa', 'rafael@studionorte.demo', 'Agenda da apresentação', 140, false, true, 'Podemos passar para as 14h? Assim o diretor participa.'),
    mail(3, 'Gmail', 'Clara Souza', 'clara@email.demo', 'Fotos do fim de semana', 300, false, false, 'Mandei as fotos no álbum compartilhado.'),
    mail(4, 'Gmail', 'Contabilidade Prisma', 'contato@prisma.demo', 'Documentos de novembro recebidos', 600, true, false, 'Recebemos tudo, obrigado.')
  ];
  var EMAILS = { configurado: true, itens: TODOS.filter(function (e) { return e.pede; }), todos: TODOS, atualizado: hm(agora),
    contas: [{ nome: 'Gmail', nao_lidos: 2, pedem: 1, erro: null }, { nome: 'iCloud', nao_lidos: 1, pedem: 1, erro: null }] };

  function usoResumo() {
    var pts = [], zonas = [[.86, .22, 18, 0], [.17, .145, 10, 0], [.2, .78, 9, 0], [.5, .78, 7, 0], [.82, .78, 8, 0], [.47, .42, 6, 0], [.62, .5, 3, 1]];
    var s = 7;
    function rnd() { s = (s * 9301 + 49297) % 233280; return s / 233280; }
    zonas.forEach(function (z) { for (var i = 0; i < z[2]; i++) pts.push([+(z[0] + (rnd() - .5) * .08).toFixed(3), +(z[1] + (rnd() - .5) * .07).toFixed(3), z[3]]); });
    return { cliques: 61, mortos: 3, raiva: 0, abas: 4, pontos: pts, ultima_avaliacao: mais(-2) };
  }
  function sistema() {
    return { wealth_hoje: ROTINAS, wealth_ontem: ROTINAS, saude_wealth: { estado: 'ok', itens: [] },
      orbitus: [{ rotina: 'backup', quando: mais(-1) + 'T23:15', status: 'ok', detalhe: 'cofre salvo' },
        { rotina: 'lembretes', quando: HOJE + 'T13:31', status: 'ok', detalhe: 'tudo registrado' },
        { rotina: 'lente', quando: mais(-2) + 'T09:25', status: 'ok', detalhe: '61 eventos · 3 propostas' }], reinicios: [] };
  }

  /* ---------- Vega (falas prontas) ---------- */
  function fala(p) {
    p = (p || '').toLowerCase();
    var tr = 'A tarefa mais urgente é enviar a proposta revisada para a Lumen, amanhã.';
    if (/bom dia/.test(p)) return 'Bom dia, ' + NOME + '. Hoje tem reunião com a equipe de produto às 10h e call com a Studio Norte às 15h30. ' + tr + ' A Beatriz, da Lumen, quer fechar até sexta. Treino de pernas te espera.';
    if (/boa tarde/.test(p)) return 'Boa tarde, ' + NOME + '. Seis copos de água, bom ritmo. Faltam 38 gramas de proteína para a meta e o treino de pernas ainda não saiu. Dois e-mails pedem resposta.';
    if (/boa noite/.test(p)) return 'Boa noite, ' + NOME + '. Amanhã cedo tem dentista às 9h. A Mesa de Finanças deixou uma decisão para você: aumentar a reserva de emergência para oito meses.';
    if (/viag|lisboa/.test(p)) return 'Lisboa em 24 dias. Falta reservar o hotel, e a tarefa já está na sua semana.';
    if (/sexta/.test(p)) return 'Boa sexta, ' + NOME + '. Semana com três treinos de cinco e todas as rotinas em dia. Antes de sair: responder a Beatriz.';
    return 'Esta é uma demonstração do Orbitus. Na versão real, eu respondo com os seus dados: agenda, tarefas, finanças, treino e viagens, por texto ou por voz.';
  }
  function sse(texto) {
    var partes = texto.match(/[^.!?]+[.!?]*\s*/g) || [texto], enc = new TextEncoder(), i = 0;
    var corpo = new ReadableStream({ pull: function (c) {
      return new Promise(function (ok) { setTimeout(function () {
        if (i < partes.length) c.enqueue(enc.encode('data: ' + JSON.stringify({ t: 'delta', x: partes[i++] }) + '\n\n'));
        else { c.enqueue(enc.encode('data: ' + JSON.stringify({ t: 'fim', resposta: texto, custo_usd: 0, mes_usd: 1.2, teto: 15 }) + '\n\n')); c.close(); }
        ok();
      }, 260); });
    } });
    return new Response(corpo, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  }

  /* ---------- interceptação ---------- */
  function json(o) { return Promise.resolve(new Response(JSON.stringify(o), { status: 200, headers: { 'Content-Type': 'application/json' } })); }
  var real = window.fetch.bind(window);
  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '', m = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    var u; try { u = new URL(url, location.href); } catch (e) { return real(input, init); }
    if (u.origin !== location.origin || u.pathname.indexOf('/api/') !== 0) return real(input, init);
    var p = u.pathname;
    if (m !== 'GET') {
      if (p === '/api/concierge/fluxo') { var b = {}; try { b = JSON.parse((init && init.body) || '{}'); } catch (e) {} return Promise.resolve(sse(fala(b.pergunta))); }
      if (p === '/api/voz') return real(input, init);                         // só sintetiza a fala pronta, nada do cofre
      return json({ ok: true, demo: true, aviso: 'demonstração: nada foi gravado' });
    }
    if (p === '/api/dados') return json(dados());
    if (p === '/api/dia') return json(dia(u.searchParams.get('d') || HOJE));
    if (p === '/api/sistema') return json(sistema());
    if (p === '/api/uso') return json(usoResumo());
    if (p === '/api/concierge') return json({ tom: 'espirituoso', configurado: true, modelo: 'demo', mes: HOJE.slice(0, 7), usd: 1.2, teto: 15, perguntas: 12 });
    if (p === '/api/voz') return real(input, init);
    if (p === '/api/push') return Promise.resolve(new Response('{}', { status: 404 }));   // sem avisos de instalação na vitrine
    return json({ disponivel: false, demo: true });                            // qualquer outra leitura: nada real
  };

  /* ---------- tela: selo, nome e abas fora da vitrine ---------- */
  var FORA = { wealth: 'Escritório Financeiro', mesa: 'Mesa de Finanças', treino: 'Treino', emails: 'E-mails', viagem: 'Viagens', agenda: 'Agenda', tarefas: 'Tarefas', sistema: 'Saúde do sistema' };
  function montar() {
    var st = document.createElement('style');
    st.textContent = '#demoSelo{position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:100001;background:rgba(255,190,80,.14);border:1px solid rgba(255,190,80,.45);color:#ffe2a8;font:500 12px Manrope,sans-serif;letter-spacing:.14em;text-transform:uppercase;padding:6px 14px;border-radius:999px;backdrop-filter:blur(10px)}' +
      '#demoSelo a{color:#ffe2a8;opacity:.7;margin-left:10px;letter-spacing:.06em;text-transform:none}' +
      '#demoAba{position:fixed;inset:0;z-index:100000;display:none;align-items:center;justify-content:center;background:rgba(4,6,11,.86);backdrop-filter:blur(14px)}' +
      '#demoAba div{max-width:440px;margin:16px;padding:28px;border-radius:20px;border:1px solid rgba(255,255,255,.12);background:rgba(14,18,28,.9);color:#e6ecff;font:15px/1.55 Manrope,sans-serif;text-align:center}' +
      '#demoAba h2{font-weight:200;font-size:28px;margin:0 0 8px}#demoAba a{display:inline-block;margin-top:16px;padding:10px 18px;border-radius:12px;border:1px solid rgba(255,255,255,.2);color:#fff;text-decoration:none}';
    document.head.appendChild(st);
    var selo = document.createElement('div'); selo.id = 'demoSelo';
    selo.innerHTML = 'Demonstração · dados fictícios<a href="/?demo=0">sair</a>';
    var aba = document.createElement('div'); aba.id = 'demoAba';
    aba.innerHTML = '<div><h2 id="demoAbaT"></h2><p>Este módulo faz parte da apresentação completa. Nesta demonstração, a vitrine é a Home e a sala dos agentes, com dados fictícios.</p><a href="#">Voltar à Home</a></div>';
    document.body.appendChild(selo); document.body.appendChild(aba);
    var g = document.querySelector('#greet + span') || document.querySelector('h1 span'); if (g) g.textContent = NOME;
    var av = document.querySelector('.avatar'); if (av) av.textContent = NOME.charAt(0);
    function rota() {
      var k = (location.hash || '').replace('#', '').split('/')[0];
      if (FORA[k]) { document.getElementById('demoAbaT').textContent = FORA[k]; aba.style.display = 'flex'; } else aba.style.display = 'none';
    }
    addEventListener('hashchange', rota); rota();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', montar); else montar();
})();
