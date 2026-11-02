/* Orbitus — rosto 3D da Vega (WebGL, three.js).
   Malha e expressões (blendshapes ARKit) do modelo "Face Cap" de Bannaflak, distribuído nos exemplos do three.js.
   Partículas sorteadas sobre a superfície, com brilho de borda azul, luz rosa e uma parte que se "esfarela".
   Lê o estado da página por window.ORBX(): nível da voz, posição do rosto, para onde olhar e se a tela está ociosa.
   Se algo falhar (sem WebGL, sem internet para o three.js), a página continua com o rosto 2D. */
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';

const hero = document.querySelector('.hero');
const X = window.ORBX;
if (!hero || !X) throw new Error('rosto3d: página sem ORBX');

const cv = document.createElement('canvas');
cv.id = 'orb3d';
cv.setAttribute('aria-hidden', 'true');
cv.style.cssText = 'position:absolute;pointer-events:none;z-index:2;';
hero.appendChild(cv);

const renderer = new THREE.WebGLRenderer({ canvas: cv, alpha: true, antialias: false, powerPreference: 'low-power' });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.setClearColor(0x000000, 0);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 50);
camera.position.set(0, 0, 8.4);
camera.lookAt(0, 0, 0);

const MOVEL = window.innerWidth < 760;
const ALVOS = ['jawOpen', 'eyeBlink_L', 'eyeBlink_R', 'mouthSmile', 'mouthFunnel', 'browInnerUp'];

/* Rosto da Vega: busto que o Marcio gerou no ChatGPT, com profundidade estimada (Depth Anything V2).
   É um relevo de frente (2,5D): bonito de frente e em giros moderados. Sem ele, cai no modelo Face Cap. */
function daVega(v) {
  const raw = Uint8Array.from(atob(v.d), c => c.charCodeAt(0)), A = new Int16Array(raw.buffer);
  const passo = MOVEL ? 2 : 1, N = Math.floor(v.n / passo);
  const pos = new Float32Array(N * 3), nor = new Float32Array(N * 3), rnd = new Float32Array(N * 2), rimk = new Float32Array(N), lum = new Float32Array(N);
  const del = {}; ALVOS.forEach(n => del[n] = new Float32Array(N * 3));
  const B = v.boca, cxB = (B.x0 + B.x1) / 2, meia = (B.x1 - B.x0) / 2;
  for (let q = 0; q < N; q++) {
    const i = q * passo * 7, x = A[i] / 20000, y = A[i + 1] / 20000, z = A[i + 2] / 20000;
    pos[q * 3] = x; pos[q * 3 + 1] = y; pos[q * 3 + 2] = z;
    nor[q * 3] = A[i + 3] / 32000; nor[q * 3 + 1] = A[i + 4] / 32000; nor[q * 3 + 2] = A[i + 5] / 32000;
    let L = A[i + 6] / 32000;
    if (y < -.7) L *= Math.max(0, 1 - (-.7 - y) / .32);          // pescoço some aos poucos
    lum[q] = L;
    // boca: queixo e lábio de baixo descem com a voz; o lábio de cima sobe um pouco
    const dx = Math.abs(x - cxB);
    if (y < B.y && y > B.queixo - .1) {
      const fx = Math.max(0, 1 - Math.pow(dx / (meia * 2.1), 2)), fy = 1 - .4 * Math.min(1, (B.y - y) / (B.y - B.queixo));
      const w = fx * fy; del.jawOpen[q * 3 + 1] = -.12 * w; del.jawOpen[q * 3 + 2] = -.03 * w;
    } else if (y >= B.y && y < B.y + .045 && dx < meia * 1.05) {
      del.jawOpen[q * 3 + 1] = .018 * (1 - (y - B.y) / .045) * (1 - dx / (meia * 1.05));
    }
    const zonaBoca = dx < meia * 1.3 && y > B.y - .08 && y < B.y + .08, zonaNariz = Math.abs(x) < .14 && y > B.y + .06 && y < B.y + .42;
    rimk[q] = zonaBoca ? .15 : zonaNariz ? .45 : 1;
    const fora = v.cabelo && (Math.abs(x) > .5 || y > .62) ? .18 : 0;   // fios de cabelo soltam mais poeira
    const borda = Math.max(0, Math.min(1, Math.max((-.02 - z) / .18, (y - (v.cabelo ? 1.15 : 1.0)) / .25, (-.7 - y) / .3) + fora));
    rnd[q * 2] = Math.random() < borda * .6 ? .9 + Math.random() * .1 : Math.random(); rnd[q * 2 + 1] = Math.random();
  }
  return { N, pos, nor, rnd, rimk, lum, del, centroY: v.cabelo ? -.13 : -.16, giro: .55, brilho: 1.7, tam: 1.25, escala: v.cabelo ? .86 : 1 };
}

async function daMalha() {
const dados = await fetch('/static/rosto/head.json').then(r => r.json());
const P = dados.p, I = dados.i, M = dados.m;
const nv = P.length / 3;
// feminização leve da malha: nariz mais fino, lábios mais cheios, mandíbula e queixo mais estreitos
for (let i = 0; i < nv; i++) {
  const k = i * 3; let x = P[k], y = P[k + 1], z = P[k + 2];
  const wn = Math.exp(-(x * x) / .02) * (y > -.3 && y < .3 ? 1 : 0) * (z > .45 ? 1 : 0); x *= 1 - .22 * wn;
  const wl = Math.exp(-(x * x) / .09 - ((y + .44) * (y + .44)) / .012) * (z > .38 ? 1 : 0); z += .03 * wl;
  if (y < -.3) x *= 1 - .09 * Math.min(1, (-.3 - y) / .6);
  P[k] = x; P[k + 1] = y; P[k + 2] = z;
}

// normais por vértice
const VN = new Float32Array(P.length);
for (let t = 0; t < I.length; t += 3) {
  const a = I[t] * 3, b = I[t + 1] * 3, c = I[t + 2] * 3;
  const ux = P[b] - P[a], uy = P[b + 1] - P[a + 1], uz = P[b + 2] - P[a + 2];
  const vx = P[c] - P[a], vy = P[c + 1] - P[a + 1], vz = P[c + 2] - P[a + 2];
  const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
  for (const k of [a, b, c]) { VN[k] += nx; VN[k + 1] += ny; VN[k + 2] += nz; }
}
// orienta as normais para fora (o arquivo pode vir com a ordem dos triângulos invertida)
let cxm = 0, cym = 0, czm = 0; for (let i = 0; i < nv; i++) { cxm += P[i * 3]; cym += P[i * 3 + 1]; czm += P[i * 3 + 2]; } cxm /= nv; cym /= nv; czm /= nv;
let orient = 0; for (let i = 0; i < nv; i++) { const k = i * 3; orient += VN[k] * (P[k] - cxm) + VN[k + 1] * (P[k + 1] - cym) + VN[k + 2] * (P[k + 2] - czm); }
const sg = orient < 0 ? -1 : 1;
for (let i = 0; i < nv; i++) { const k = i * 3, l = (Math.hypot(VN[k], VN[k + 1], VN[k + 2]) || 1) * sg; VN[k] /= l; VN[k + 1] /= l; VN[k + 2] /= l; }

// sorteio de pontos pela área dos triângulos
const areas = [], acc = [];
let tot = 0;
for (let t = 0; t < I.length; t += 3) {
  const a = I[t] * 3, b = I[t + 1] * 3, c = I[t + 2] * 3;
  const ux = P[b] - P[a], uy = P[b + 1] - P[a + 1], uz = P[b + 2] - P[a + 2];
  const vx = P[c] - P[a], vy = P[c + 1] - P[a + 1], vz = P[c + 2] - P[a + 2];
  // fora: o "saco" interno da boca (fica atrás dos lábios)
  const mx = (P[a] + P[b] + P[c]) / 3, my = (P[a + 1] + P[b + 1] + P[c + 1]) / 3, mz = (P[a + 2] + P[b + 2] + P[c + 2]) / 3;
  const fnx = uy * vz - uz * vy, fny = uz * vx - ux * vz, fnz = ux * vy - uy * vx, fl = Math.hypot(fnx, fny, fnz) || 1;
  const zonaBoca = Math.abs(mx) < .46 && my > -.7 && my < -.25;
  const dentro = zonaBoca && (mz < .4 || (Math.abs(fnz / fl) < .18 && mz < .5) || (Math.abs(mx) > .2 && Math.abs(fnz / fl) < .35 && mz < .56));
  const atras = mz < -.12 || Math.abs(mx) > .84;          // nuca e orelhas fora: fica a máscara do rosto
  tot += (dentro || atras) ? 0 : fl / 2; acc.push(tot);
}
const N = MOVEL ? 26000 : 52000;
const pos = new Float32Array(N * 3), nor = new Float32Array(N * 3), rnd = new Float32Array(N * 2), rimk = new Float32Array(N);
const del = {}; ALVOS.forEach(n => del[n] = new Float32Array(N * 3));
const lum = new Float32Array(N).fill(1);
function morph(n, vi) {
  if (n === 'mouthSmile') { const L = M.mouthSmile_L, R = M.mouthSmile_R, k = vi * 3; return [L[k] + R[k], L[k + 1] + R[k + 1], L[k + 2] + R[k + 2]]; }
  const A = M[n], k = vi * 3; return [A[k], A[k + 1], A[k + 2]];
}
for (let q = 0; q < N; q++) {
  const r = Math.random() * tot; let lo = 0, hi = acc.length - 1;
  while (lo < hi) { const m = (lo + hi) >> 1; if (acc[m] < r) lo = m + 1; else hi = m; }
  const t = lo * 3, ia = I[t], ib = I[t + 1], ic = I[t + 2];
  let u = Math.random(), w = Math.random(); if (u + w > 1) { u = 1 - u; w = 1 - w; } const v0 = 1 - u - w;
  for (let k = 0; k < 3; k++) {
    pos[q * 3 + k] = P[ia * 3 + k] * v0 + P[ib * 3 + k] * u + P[ic * 3 + k] * w;
    nor[q * 3 + k] = VN[ia * 3 + k] * v0 + VN[ib * 3 + k] * u + VN[ic * 3 + k] * w;
  }
  for (const n of ALVOS) { const A = morph(n, ia), B = morph(n, ib), C = morph(n, ic); for (let k = 0; k < 3; k++) del[n][q * 3 + k] = A[k] * v0 + B[k] * u + C[k] * w; }
  // bordas (testa alta, laterais, queixo) se esfarelam mais
  const qx = pos[q * 3], qy = pos[q * 3 + 1], qz = pos[q * 3 + 2];
  const borda = Math.max(0, Math.min(1, Math.max((qy - .55) / .5, (.25 - qz) / .35, (-.75 - qy) / .2)));
  rimk[q] = (Math.abs(qx) < .5 && qy > -.72 && qy < -.12) ? .08 : (Math.abs(qx) < .25 && qy > -.3 && qy < .3 && qz > .45 ? .5 : 1);   // sem brilho de borda nas dobras da boca e do nariz
  rnd[q * 2] = Math.random() < borda * .6 ? .9 + Math.random() * .1 : Math.random(); rnd[q * 2 + 1] = Math.random();
}
  return { N, pos, nor, rnd, rimk, lum, del, centroY: -.21, giro: 1.1, brilho: 1, tam: 1, escala: 1 };
}

const vegaDados = await fetch('/static/rosto/vega.json?v=cabelo1').then(r => r.ok ? r.json() : null).catch(() => null);
const { N, pos, nor, rnd, rimk, lum, del, centroY, giro, brilho, tam, escala } = vegaDados ? daVega(vegaDados) : await daMalha();
const geo = new THREE.BufferGeometry();
geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
geo.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
geo.setAttribute('aRnd', new THREE.BufferAttribute(rnd, 2));
geo.setAttribute('aRimK', new THREE.BufferAttribute(rimk, 1));
geo.setAttribute('aLum', new THREE.BufferAttribute(lum, 1));
geo.setAttribute('dJaw', new THREE.BufferAttribute(del.jawOpen, 3));
geo.setAttribute('dBlink', new THREE.BufferAttribute(del.eyeBlink_L.map((v, i) => v + del.eyeBlink_R[i]), 3));
geo.setAttribute('dSmile', new THREE.BufferAttribute(del.mouthSmile, 3));
geo.setAttribute('dFunnel', new THREE.BufferAttribute(del.mouthFunnel, 3));
geo.setAttribute('dBrow', new THREE.BufferAttribute(del.browInnerUp, 3));
geo.computeBoundingSphere();

const U = {
  uTime: { value: 0 }, uJaw: { value: 0 }, uBlink: { value: 0 }, uSmile: { value: .12 }, uFunnel: { value: 0 }, uBrow: { value: 0 },
  uSize: { value: 1 }, uPensa: { value: 0 }, uBrilho: { value: 1 },
};
const mat = new THREE.ShaderMaterial({
  uniforms: U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  vertexShader: `
    attribute vec2 aRnd; attribute float aRimK; attribute float aLum; attribute vec3 dJaw, dBlink, dSmile, dFunnel, dBrow;
    uniform float uTime, uJaw, uBlink, uSmile, uFunnel, uBrow, uSize, uPensa, uBrilho;
    varying float vRim, vKey, vA, vFace, vLum, vGrad;
    void main(){
      vLum = aLum;
      vGrad = clamp(.55 - .38*position.y + .22*position.x, 0., 1.);   // azul em cima, rosa embaixo
      vec3 p = position + uJaw*dJaw + uBlink*dBlink + uSmile*dSmile + uFunnel*dFunnel + uBrow*dBrow;
      // esfarelado: ~12% dos pontos se soltam aos poucos da pele e caem como poeira
      float solta = step(.88, aRnd.x);
      float ph = fract(uTime*(.04+.05*aRnd.y) + aRnd.x*13.7);
      p += normal*(.006*sin(uTime*1.7 + aRnd.y*40.) + uPensa*.01*sin(uTime*5. + p.y*12.));
      p += solta*(normal*ph*.35 + vec3(.05*sin(aRnd.y*30.), -ph*.25, 0.));
      vec4 mv = modelViewMatrix*vec4(p,1.);
      vec3 N = normalize(normalMatrix*normal), V = normalize(-mv.xyz);
      float ndv = dot(N,V);
      vFace = ndv;
      vRim = pow(1. - clamp(ndv,0.,1.), 2.6) * aRimK;
      vKey = max(dot(N, normalize(vec3(-.35,.55,.75))), 0.);
      vA = solta > .5 ? (1.-ph)*.7 : 1.;
      gl_PointSize = uSize*(.55 + aRnd.y*.9)*(solta > .5 ? .8 : 1.)/(-mv.z);
      gl_Position = projectionMatrix*mv;
    }`,
  fragmentShader: `
    uniform float uBrilho;
    varying float vRim, vKey, vA, vFace, vLum, vGrad;
    void main(){
      if (vLum < .02) discard;
      if (vFace < -.08) discard;
      vec2 c = gl_PointCoord - .5; float d = dot(c,c); if (d > .25) discard;
      float disco = 1. - smoothstep(.05, .25, d);
      vec3 base = vec3(.10,.07,.32);
      vec3 rosa = mix(vec3(.42,.52,1.), vec3(1.,.42,.85), vGrad);
      vec3 azul = vec3(.28,.62,1.);
      vec3 cor = base*.6 + rosa*pow(vKey,1.6)*.85 + azul*vRim*1.5;
      float tom = smoothstep(.22, .9, vLum);             // sobrancelhas, cílios e a linha da boca ficam escuros, como na foto
      cor *= .45 + .55*tom;
      float a = (.16 + .55*pow(vKey,1.3) + .9*vRim) * vA * disco * (.2 + .8*tom);
      a = min(1., a*uBrilho);
      gl_FragColor = vec4(cor*a, a);
    }`,
});
U.uBrilho.value = brilho;
const pontos = new THREE.Points(geo, mat);
const cabeca = new THREE.Group();
cabeca.add(pontos);
scene.add(cabeca);
pontos.position.y = centroY * escala; pontos.scale.setScalar(escala);   // centro da cabeça no meio do quadro

// layout: o canvas é um quadrado centrado onde a página desenharia o rosto
let lado = 0;
function encaixar(s) {
  const L = Math.round(s.R * 1.75);
  if (L !== lado) { lado = L; renderer.setSize(L, L, false); cv.style.width = L + 'px'; cv.style.height = L + 'px'; camera.aspect = 1; camera.updateProjectionMatrix(); U.uSize.value = L * .026 * tam * (MOVEL ? 1.3 : 1) * Math.min(devicePixelRatio || 1, 2); }
  cv.style.left = Math.round(s.cx - L / 2) + 'px';
  cv.style.top = Math.round(s.cy - L * .5) + 'px';
}

let piscar = 0, proxPiscar = performance.now() + 2500, ult = 0, t0 = performance.now(), mouth = 0;
function quadro(now) {
  requestAnimationFrame(quadro);
  const s = X();
  if (document.hidden || (s.ocioso && !s.fala) || !s.R) return;
  if (now - ult < 33) return;
  ult = now;
  encaixar(s);
  const t = (now - t0) / 1000;
  // boca: abre com o volume da voz, com um pouco de bico para parecer fala e não mastigação
  const alvo = s.fala ? Math.min(1, s.lvl * 1.7) : 0;
  mouth += (alvo - mouth) * .45;
  U.uJaw.value = mouth * .55;
  U.uFunnel.value = s.fala ? .25 * Math.abs(Math.sin(t * 7.3)) * mouth : 0;
  U.uSmile.value = s.fala ? .03 : .06 + .03 * Math.sin(t * .4);
  U.uBrow.value = s.pensa ? .35 : (s.fala ? .12 * mouth : 0);
  U.uPensa.value = s.pensa ? 1 : 0;
  // piscar a cada 2,5 a 6 s
  if (now > proxPiscar) { piscar = 1; proxPiscar = now + 2500 + Math.random() * 3500; }
  // olhos semicerrados e serenos (como na referência); abrem um pouco quando fala e fecham de vez numa piscada
  const aberto = s.fala ? .86 : .97;
  U.uBlink.value = Math.min(1, aberto + (piscar > 0 ? .4 * Math.sin(Math.min(1, piscar) * Math.PI) : 0));
  if (piscar > 0) piscar -= .2; if (piscar < 0) piscar = 0;
  U.uTime.value = t;
  cabeca.rotation.y = s.yaw * giro;
  cabeca.rotation.x = -s.pitch * giro;
  renderer.render(scene, camera);
}
window.ROSTO3D_OK = true;
requestAnimationFrame(quadro);
