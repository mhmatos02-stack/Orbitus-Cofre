/* Orbitus · coleta de uso para o Lente (UX/UI) e o mapa de calor.
   Grava SÓ posição, elemento (tag/id/classe) e aba. Nunca texto, título, valor digitado ou conteúdo.
   Dados: 00_Sistema/uso/AAAA-MM.jsonl (via POST /api/uso). Mapa de calor: abra o painel com ?calor=1. */
(function(){
  if (window.__USO__) return; window.__USO__ = true;
  try { if (window.ORBITUS_DEMO || (window.top !== window && window.top.ORBITUS_DEMO)) return; } catch (e) {}   // demonstração não entra no mapa de calor
  var DENTRO = window.top !== window;                       // treino.html roda dentro do painel
  var FILA = [], ULT = {aba: null, desde: Date.now()};
  function aba(){ if (DENTRO) return 'treino'; var h = (location.hash || '').replace('#','').split('/')[0]; return h || 'home'; }
  function seletor(el){                                      // caminho curto sem texto: tag#id.classe
    var p = [], n = 0;
    while (el && el.nodeType === 1 && n < 4) {
      var s = el.tagName.toLowerCase();
      if (el.id) { p.unshift(s + '#' + el.id); break; }
      var c = (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/)[0];
      if (c) s += '.' + c.replace(/[^\w-]/g,'').slice(0,24);
      p.unshift(s); el = el.parentElement; n++;
    }
    return p.join('>').slice(0,120);
  }
  function interativo(el){ return !!(el && el.closest && el.closest('a,button,input,select,textarea,label,summary,[role=button],[onclick],[tabindex]')); }
  function pos(e){ return {x: +(e.clientX / innerWidth).toFixed(3), y: Math.round(e.clientY + scrollY), vw: innerWidth, vh: innerHeight}; }
  function registrar(o){ o.em = new Date().toISOString().slice(0,19); o.aba = o.aba || aba(); FILA.push(o); if (FILA.length >= 40) enviar(); }
  function enviar(){
    if (!FILA.length) return; var lote = FILA.splice(0, FILA.length);
    try { fetch('/api/uso', {method:'POST', keepalive:true, headers:{'Content-Type':'application/json'}, body: JSON.stringify({eventos: lote})}).catch(function(){}); } catch(e){}
  }
  var ultClique = {t:0, x:0, y:0, n:0};
  addEventListener('pointerdown', function(e){
    if (CALOR.ativo) return;
    var el = e.target, p = pos(e), agora = Date.now();
    var perto = Math.abs(e.clientX - ultClique.x) < 30 && Math.abs(e.clientY - ultClique.y) < 30 && agora - ultClique.t < 700;
    ultClique.n = perto ? ultClique.n + 1 : 1; ultClique.t = agora; ultClique.x = e.clientX; ultClique.y = e.clientY;
    p.ev = 'clique'; p.alvo = seletor(el); p.morto = !interativo(el); if (ultClique.n >= 3) p.raiva = ultClique.n;
    registrar(p);
  }, {capture:true, passive:true});
  function trocaAba(){
    if (DENTRO) return;                                      // dentro do painel quem conta aba e tempo é o painel
    var a = aba(), agora = Date.now();
    if (ULT.aba && ULT.aba !== a) registrar({ev:'tempo', aba: ULT.aba, seg: Math.round((agora - ULT.desde)/1000)});
    if (ULT.aba !== a) { registrar({ev:'aba', aba: a}); ULT.aba = a; ULT.desde = agora; }
  }
  addEventListener('hashchange', trocaAba);
  document.addEventListener('visibilitychange', function(){
    if (document.hidden) { if (!DENTRO) registrar({ev:'tempo', aba: aba(), seg: Math.round((Date.now() - ULT.desde)/1000)}); enviar(); }
    else { ULT.desde = Date.now(); }
  });
  setInterval(enviar, 30000);
  trocaAba();

  /* ---------- mapa de calor (?calor=1, só no painel principal) ---------- */
  var CALOR = {ativo: !DENTRO && /[?&]calor=1/.test(location.search)};
  if (!CALOR.ativo) return;
  var cv = document.createElement('canvas'), leg = document.createElement('div'), DADOS = [];
  cv.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:99999';
  leg.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:100000;background:rgba(10,14,22,.88);color:#e6ecff;font:12px Manrope,sans-serif;padding:10px 14px;border:1px solid rgba(255,255,255,.15);border-radius:12px;max-width:280px;line-height:1.5';
  document.body.appendChild(cv); document.body.appendChild(leg);
  function desenhar(){
    var dpr = Math.min(devicePixelRatio || 1, 2), W = innerWidth, H = innerHeight, g = cv.getContext('2d'), a = aba();
    cv.width = W*dpr; cv.height = H*dpr; g.setTransform(dpr,0,0,dpr,0,0); g.clearRect(0,0,W,H);
    var pts = DADOS.filter(function(d){ return d.ev === 'clique' && d.aba === a && Math.abs(d.vw - W)/W < 0.2; });
    g.globalCompositeOperation = 'lighter';
    pts.forEach(function(d){
      var x = d.x*W, y = d.y - scrollY; if (y < -40 || y > H + 40) return;
      var r = g.createRadialGradient(x,y,0,x,y,28), cor = d.morto ? '255,93,140' : '255,190,80';
      r.addColorStop(0,'rgba('+cor+',.35)'); r.addColorStop(1,'rgba('+cor+',0)'); g.fillStyle = r; g.beginPath(); g.arc(x,y,28,0,6.283); g.fill();
    });
    var mortos = pts.filter(function(d){return d.morto}).length, raiva = pts.filter(function(d){return d.raiva}).length;
    var tempo = DADOS.filter(function(d){return d.ev==='tempo' && d.aba===a}).reduce(function(s,d){return s+(d.seg||0)},0);
    leg.innerHTML = '<b>Mapa de calor · ' + a + '</b><br>' + pts.length + ' cliques nos últimos 30 dias (telas de largura parecida)<br>' +
      '<span style="color:#ffbe50">●</span> clique em algo clicável &nbsp; <span style="color:#ff5d8c">●</span> clique em algo que não faz nada (' + mortos + ')<br>' +
      (raiva ? raiva + ' sequência(s) de cliques repetidos (frustração)<br>' : '') +
      'Tempo nesta aba: ' + Math.round(tempo/60) + ' min<br><span style="opacity:.6">Troque de aba para ver as outras. Tire ?calor=1 do endereço para fechar.</span>';
  }
  fetch('/api/uso?dias=30').then(function(r){return r.json()}).then(function(j){ DADOS = j.eventos || []; desenhar(); });
  addEventListener('scroll', desenhar, {passive:true}); addEventListener('resize', desenhar); addEventListener('hashchange', function(){ setTimeout(desenhar, 300); });
})();
