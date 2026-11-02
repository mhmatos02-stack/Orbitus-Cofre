/* Orbitus — esfera da Vega (WebGL, three.js): esfera de pontos em meio-tom, com dobras que ondulam.
   Rosa em cima, azul embaixo. Quando a Vega fala, as dobras crescem e ganham pressa; pensando, pulsa devagar.
   Segue o mouse de leve. Lê o estado da página por window.ORBX(). Se falhar, a página fica com o anel 2D. */
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';

const hero = document.querySelector('.hero');
const X = window.ORBX;
if (!hero || !X) throw new Error('esfera3d: página sem ORBX');

const cv = document.createElement('canvas');
cv.id = 'orb3d';
cv.setAttribute('aria-hidden', 'true');
cv.style.cssText = 'position:absolute;pointer-events:none;z-index:2;';
hero.appendChild(cv);

const renderer = new THREE.WebGLRenderer({ canvas: cv, alpha: true, antialias: false, powerPreference: 'low-power' });
const DPR = Math.min(devicePixelRatio || 1, 2);
renderer.setPixelRatio(DPR);
renderer.setClearColor(0x000000, 0);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 50);
camera.position.set(0, 0, 8.4);

// pontos espalhados por igual na esfera (espiral de Fibonacci): dá o padrão de meio-tom regular
const MOVEL = window.innerWidth < 760;
const N = MOVEL ? 9000 : 16000;
const pos = new Float32Array(N * 3), rnd = new Float32Array(N);
const ga = Math.PI * (3 - Math.sqrt(5));
for (let i = 0; i < N; i++) {
  const y = 1 - (i + .5) / N * 2, r = Math.sqrt(1 - y * y), a = i * ga;
  pos[i * 3] = Math.cos(a) * r; pos[i * 3 + 1] = y; pos[i * 3 + 2] = Math.sin(a) * r;
  rnd[i] = Math.random();
}
const geo = new THREE.BufferGeometry();
geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
geo.setAttribute('aRnd', new THREE.BufferAttribute(rnd, 1));

const U = { uTime: { value: 0 }, uAmp: { value: .1 }, uVel: { value: 1 }, uFala: { value: 0 }, uSize: { value: 1 }, uPensa: { value: 0 } };
const mat = new THREE.ShaderMaterial({
  uniforms: U, transparent: true, depthTest: true, depthWrite: true,
  vertexShader: `
    attribute float aRnd;
    uniform float uTime, uAmp, uVel, uFala, uSize, uPensa;
    varying float vLuz, vY, vDobra, vFrente;
    float crista(vec3 n, float t){ return pow(1. - abs(sin(2.6*(n.x*.55 + n.y*.75 + .35*n.z) - t*.5 + .8*sin(1.7*n.z + t*.3))), 5.); }
    float onda(vec3 n, float t){
      // dobras largas e lentas + cristas finas em diagonal (como um tecido torcido)
      float a = sin(2.3*n.x + 1.7*n.y + t*.55) * sin(2.1*n.z - 1.3*n.y + t*.4);
      float c = uFala * sin(9.*n.y + 6.*n.x - t*6.) * .3;          // ondinhas rápidas enquanto fala
      return a*.6 + .9*crista(n, t) + c;
    }
    void main(){
      vec3 n = normalize(position);
      float t = uTime*uVel;
      float d = onda(n, t);
      float pulso = uPensa*.04*sin(uTime*3.);
      vec3 p = n*(1. + uAmp*d + pulso);
      // normal aproximada a partir da onda (para a luz realçar as dobras)
      float e = .02;
      vec3 tx = normalize(cross(n, vec3(0.,1.,0.)) + vec3(1e-4));
      vec3 ty = normalize(cross(n, tx));
      float dx = onda(normalize(n + tx*e), t) - d, dy = onda(normalize(n + ty*e), t) - d;
      vec3 nn = normalize(n - (tx*dx + ty*dy)*uAmp/e*.9);
      vec4 mv = modelViewMatrix*vec4(p,1.);
      vec3 N = normalize(normalMatrix*nn);
      vec3 L = normalize(vec3(-.25,.45,.85));
      vLuz = max(dot(N,L),0.)*.85 + .35*max(dot(N, normalize(vec3(.2,-.7,.6))),0.);   // luz principal em cima + contraluz azul embaixo
      vDobra = crista(n, t);                               // cristas das dobras brilham mais
      vY = n.y;
      vFrente = dot(normalize(normalMatrix*n), vec3(0.,0.,1.));
      // meio-tom: o ponto cresce onde há luz
      gl_PointSize = uSize*(.3 + 1.*pow(vLuz,1.5) + .6*vDobra)/(-mv.z);
      gl_Position = projectionMatrix*mv;
    }`,
  fragmentShader: `
    varying float vLuz, vY, vDobra, vFrente;
    void main(){
      vec2 c = gl_PointCoord - .5; if (dot(c,c) > .25) discard;
      vec3 rosa = vec3(1., .38, .72), lilas = vec3(.62, .3, .95), azul = vec3(.34, .4, 1.);
      float g = smoothstep(-1., 1., vY);
      vec3 cor = g > .5 ? mix(lilas, rosa, (g-.5)*2.) : mix(azul, lilas, g*2.);
      float a = .35 + .65*pow(vLuz, 1.4) + .7*vDobra;
      a *= smoothstep(-.35, .25, vFrente);                 // o fundo da esfera fica escuro, como na referência
      cor = cor*(.5 + .8*pow(vLuz,1.4)) + vec3(1.,.85,.95)*vDobra*.45;
      gl_FragColor = vec4(cor, clamp(a,0.,1.));
    }`,
});
const pontos = new THREE.Points(geo, mat);
const grupo = new THREE.Group();
grupo.add(pontos);
grupo.scale.setScalar(1.05);
scene.add(grupo);

let lado = 0;
function encaixar(s) {
  const L = Math.round(s.R * 1.75);
  if (L !== lado) { lado = L; renderer.setSize(L, L, false); cv.style.width = L + 'px'; cv.style.height = L + 'px'; U.uSize.value = L * .021 * DPR * (MOVEL ? 1.2 : 1); }
  cv.style.left = Math.round(s.cx - L / 2) + 'px';
  cv.style.top = Math.round(s.cy - L / 2) + 'px';
}

let ult = 0, t0 = performance.now(), fala = 0;
function quadro(now) {
  requestAnimationFrame(quadro);
  const s = X();
  if (document.hidden || (s.ocioso && !s.fala) || !s.R) return;
  if (now - ult < 33) return;
  ult = now;
  encaixar(s);
  const alvo = s.fala ? Math.min(1, .35 + s.lvl * 1.4) : 0;
  fala += (alvo - fala) * .2;
  U.uFala.value = fala;
  U.uAmp.value = .17 + .14 * fala;
  U.uVel.value = 1 + 1.8 * fala;
  U.uPensa.value = s.pensa ? 1 : 0;
  U.uTime.value = (now - t0) / 1000;
  grupo.rotation.y = s.yaw * .8 + U.uTime.value * .05;
  grupo.rotation.x = -s.pitch * .8;
  renderer.render(scene, camera);
}
window.ESFERA3D_OK = true;
requestAnimationFrame(quadro);
