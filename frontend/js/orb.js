// The home page centrepiece: a SAGE wristband drawn in points of light that flows into a heart, then a
// heartbeat line, and back (after the particle-sculpture hero in the "keep it simple? no" portfolio short).
// Three.js from the import map in home.html. Decorative: the wrapper carries the text alternative.
// Reduced motion: one still heart. No WebGL: the CSS glow behind it stays on its own.
import * as THREE from "three";

const canvas = document.getElementById("orb-canvas");
const steps = [...document.querySelectorAll(".orb-steps li")];
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const small = matchMedia("(max-width: 40rem)").matches;
const N = small ? 3200 : 7000;

// ---------- Shapes (each an array of N points) ----------
const rnd = (a, b) => a + Math.random() * (b - a);
function band() {
  const p = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) {
    let x, y, z;
    if (i < N * 0.12) {
      // the band's face: a rounded slab on the front of the ring
      x = rnd(-0.55, 0.55); y = rnd(-0.42, 0.42); z = 1.62 + rnd(0, 0.16);
    } else {
      const a = Math.random() * Math.PI * 2, w = rnd(-0.38, 0.38), r = 1.55 + rnd(-0.05, 0.05);
      x = w; y = Math.sin(a) * r; z = Math.cos(a) * r;
    }
    // tilt the ring so it reads as a band on a wrist
    const tx = 0.5, ty = -0.6;
    let y1 = y * Math.cos(tx) - z * Math.sin(tx), z1 = y * Math.sin(tx) + z * Math.cos(tx);
    let x2 = x * Math.cos(ty) + z1 * Math.sin(ty), z2 = -x * Math.sin(ty) + z1 * Math.cos(ty);
    p.set([x2, y1, z2], i * 3);
  }
  return p;
}
function heart() {
  const p = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) {
    const t = Math.random() * Math.PI * 2, s = Math.pow(Math.random(), 0.35); // most points near the surface
    const hx = 16 * Math.pow(Math.sin(t), 3);
    const hy = 13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t);
    const k = 0.105 * s;
    const depth = 0.75 * Math.sqrt(Math.max(0, 1 - s * s)) + 0.12;
    p.set([hx * k, hy * k + 0.25, rnd(-depth, depth)], i * 3);
  }
  return p;
}
function ecg(x) {
  // one heartbeat repeated: small P bump, sharp QRS spike, rounded T wave
  const u = ((x + 2.9) % 1.9 + 1.9) % 1.9 - 0.95;
  const g = (c, w, h) => h * Math.exp(-((u - c) ** 2) / (2 * w * w));
  return g(-0.45, 0.06, 0.18) + g(-0.05, 0.02, -0.25) + g(0, 0.025, 1.25) + g(0.06, 0.025, -0.45) + g(0.42, 0.1, 0.32);
}
function pulse() {
  // sample evenly along the line's length, so the tall spikes get as many points as the flat parts
  const X0 = -1.75, X1 = 2.15, M = 1600, xs = [], ys = [], len = [0];
  for (let k = 0; k <= M; k++) { const x = X0 + (X1 - X0) * k / M; xs.push(x); ys.push(ecg(x) * 1.15 - 0.2); }
  for (let k = 1; k <= M; k++) len.push(len[k - 1] + Math.hypot(xs[k] - xs[k - 1], ys[k] - ys[k - 1]));
  const total = len[M], p = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) {
    const L = Math.random() * total;
    let lo = 0, hi = M;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (len[mid] < L) lo = mid; else hi = mid; }
    const f = (L - len[lo]) / (len[hi] - len[lo] || 1);
    const x = xs[lo] + (xs[hi] - xs[lo]) * f, y = ys[lo] + (ys[hi] - ys[lo]) * f;
    const r = Math.pow(Math.random(), 2) * 0.07, a = Math.random() * Math.PI * 2;
    p.set([x + Math.cos(a) * r * 0.5, y + Math.sin(a) * r, Math.cos(a) * r * 3 + rnd(-0.1, 0.1)], i * 3);
  }
  return p;
}

function start() {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 50);
  camera.position.set(0, 0, 7);

  const shapes = [band(), heart(), pulse()];
  const pos = new Float32Array(shapes[0]);
  const delay = new Float32Array(N).map(() => Math.random());
  const phase = new Float32Array(N).map(() => Math.random() * Math.PI * 2);
  const warm = new Uint8Array(N).map(() => (Math.random() < 0.08 ? 1 : 0)); // a sprinkle of coral for warmth

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const col = new Float32Array(N * 3);
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));

  // round, soft sprite
  const dot = document.createElement("canvas"); dot.width = dot.height = 64;
  const c = dot.getContext("2d"), grd = c.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, "rgba(255,255,255,1)"); grd.addColorStop(0.45, "rgba(255,255,255,.85)"); grd.addColorStop(1, "rgba(255,255,255,0)");
  c.fillStyle = grd; c.fillRect(0, 0, 64, 64);
  const mat = new THREE.PointsMaterial({ size: small ? 0.05 : 0.042, map: new THREE.CanvasTexture(dot), vertexColors: true, transparent: true, depthWrite: false });
  const points = new THREE.Points(geo, mat);
  const group = new THREE.Group(); group.add(points); scene.add(group);

  // colours follow the theme: mint and coral tokens; glowing (additive) on dark, solid on light
  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim().split(/\s+/).map((v) => +v / 255);
  function paint() {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    const mint = token("--accent-display"), coral = token("--accent-2");
    for (let i = 0; i < N; i++) {
      const [r, g, b] = warm[i] ? coral : mint, j = 0.8 + Math.random() * 0.2;
      col.set([r * j, g * j, b * j], i * 3);
    }
    geo.attributes.color.needsUpdate = true;
    mat.blending = dark ? THREE.AdditiveBlending : THREE.NormalBlending;
    mat.opacity = dark ? 0.9 : 1;
    mat.needsUpdate = true;
  }
  paint();
  new MutationObserver(paint).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  function layout() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    // desktop: the shape sits right of the copy; phone: centred above it
    const wide = w > 960;
    // phone: sit in the space above the copy (the top ~40% of the hero)
    const visibleH = 2 * Math.tan((camera.fov * Math.PI) / 360) * camera.position.z;
    group.position.set(wide ? 1.55 : 0, wide ? 0.1 : visibleH * 0.27, 0);
    group.scale.setScalar(wide ? 1 : Math.min(0.62, w / 640));
  }
  layout(); addEventListener("resize", layout);

  // ---------- Morph timing ----------
  const HOLD = 3.4, MORPH = 1.8;
  // ?shape=band|heart|pulse starts on that shape (handy for screenshots and checking each one)
  const first = Math.max(0, ["band", "heart", "pulse"].indexOf(new URLSearchParams(location.search).get("shape")));
  let from = first, to = first, morphStart = -1, holdUntil = HOLD, clock = 0, last = performance.now();
  pos.set(shapes[first]);
  const setStep = (k) => steps.forEach((li, i) => li.classList.toggle("is-on", i === k));
  setStep(first);
  if (steps.length) steps[0].parentElement.hidden = false;

  let mx = 0, my = 0;
  addEventListener("pointermove", (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });

  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now; clock += dt;
    if (morphStart < 0 && clock > holdUntil) { from = to; to = (to + 1) % shapes.length; morphStart = clock; setStep(to); }
    let t = 1;
    if (morphStart >= 0) {
      t = (clock - morphStart) / MORPH;
      if (t >= 1) { t = 1; morphStart = -1; from = to; holdUntil = clock + HOLD; }
    }
    const A = shapes[from], B = shapes[to];
    for (let i = 0; i < N; i++) {
      const k = ease(Math.min(1, Math.max(0, (t - delay[i] * 0.35) / 0.65)));
      const w = Math.sin(clock * 1.3 + phase[i]) * 0.018;
      const o = i * 3;
      pos[o] = A[o] + (B[o] - A[o]) * k + w;
      pos[o + 1] = A[o + 1] + (B[o + 1] - A[o + 1]) * k + w;
      pos[o + 2] = A[o + 2] + (B[o + 2] - A[o + 2]) * k;
    }
    geo.attributes.position.needsUpdate = true;
    group.rotation.y += (mx * 0.5 + Math.sin(clock * 0.25) * 0.25 - group.rotation.y) * 0.04;
    group.rotation.x += (my * 0.3 - group.rotation.x) * 0.04;
    renderer.render(scene, camera);
  }

  if (reduced) {
    // one still heart, no motion
    pos.set(shapes[1]); geo.attributes.position.needsUpdate = true; setStep(1);
    renderer.render(scene, camera);
    addEventListener("resize", () => renderer.render(scene, camera));
    new MutationObserver(() => renderer.render(scene, camera)).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return;
  }

  // run only while the hero is on screen and the tab is visible
  let onScreen = true;
  const loop = () => { last = performance.now(); renderer.setAnimationLoop(onScreen && !document.hidden ? frame : null); };
  new IntersectionObserver((e) => { onScreen = e[0].isIntersecting; loop(); }).observe(canvas);
  document.addEventListener("visibilitychange", loop);
  loop();
}

try { start(); } catch (err) { canvas.remove(); console.warn("SAGE orb: WebGL unavailable, showing the still glow.", err); }
