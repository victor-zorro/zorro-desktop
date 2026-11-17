// zorro greeter — background effects.
// A wireframe whale is drawn on a 2D canvas, then fed as a texture into a
// WebGL shader that adds the chaos: CRT power-on, TV static, film grain,
// dust, scratches, tearing, chromatic split and colour bars.
// Exposes window.FX = { burst(strength, ms), powerOff(cb), onBurst(fn) }.
(() => {
  'use strict';

  const DPR = 1;                 // greeter runs at native res; keep it cheap
  const WHALE_SCALE = 0.75;      // whale canvas resolution vs screen
  const START = performance.now();

  // ---------- canvases -------------------------------------------------------
  const glc = document.getElementById('fx');
  const gl = glc.getContext('webgl', { antialias: false, alpha: false, preserveDrawingBuffer: false });
  const wc = document.createElement('canvas');
  const wx = wc.getContext('2d');
  let W = 0, H = 0;

  function resize() {
    W = Math.floor(innerWidth * DPR); H = Math.floor(innerHeight * DPR);
    glc.width = W; glc.height = H;
    wc.width = Math.floor(W * WHALE_SCALE); wc.height = Math.floor(H * WHALE_SCALE);
    if (gl) gl.viewport(0, 0, W, H);
  }
  addEventListener('resize', resize);
  resize();

  // ---------- shader ---------------------------------------------------------
  const VS = `
    attribute vec2 p; varying vec2 vUv;
    void main(){ vUv = p*0.5+0.5; gl_Position = vec4(p,0.,1.); }`;

  const FS = `
    precision highp float;
    varying vec2 vUv;
    uniform vec2  uRes;
    uniform float uTime, uStatic, uBurst, uBars, uPower, uSeed;
    uniform sampler2D uWhale;

    float h11(float p){ p = fract(p*.1031); p *= p+33.33; p *= p+p; return fract(p); }
    float h21(vec2 p){ vec3 q = fract(vec3(p.xyx)*.1031); q += dot(q, q.yzx+33.33); return fract((q.x+q.y)*q.z); }

    vec3 bars(float x){
      float i = floor(clamp(x,0.,.999)*7.);
      if(i<1.) return vec3(.78,.78,.78);
      if(i<2.) return vec3(.78,.78,.05);
      if(i<3.) return vec3(.05,.78,.78);
      if(i<4.) return vec3(.05,.78,.05);
      if(i<5.) return vec3(.78,.05,.78);
      if(i<6.) return vec3(.78,.05,.05);
      return vec3(.05,.05,.78);
    }

    void main(){
      vec2 frag = gl_FragCoord.xy;
      float t  = uTime;
      float fr = floor(t*24.);                 // film frame clock

      // CRT power: a dot grows into a line, then the line opens up
      vec2 c = vUv - .5;
      float px = smoothstep(0., .3, uPower);
      float py = mix(.003, 1., smoothstep(.3, 1., uPower));
      if (abs(c.x) > px*.5 || abs(c.y) > py*.5) { gl_FragColor = vec4(0,0,0,1); return; }
      vec2 uv = vec2(c.x, c.y/py) + .5;

      // gate weave
      uv += vec2(h11(fr)-.5, h11(fr+3.)-.5) * .0012;

      // horizontal tearing in bands while glitching
      float nb    = mix(6., 48., h11(uSeed));
      float band  = floor(uv.y*nb);
      float bh    = h21(vec2(band, floor(t*18.)+uSeed));
      float shift = bh > 1. - .45*uBurst ? (h11(band*1.7+uSeed)-.5) * .3 * uBurst : 0.;
      // vertical roll while the set is warming up
      float roll  = uStatic * fract(t*.9) * .35;
      vec2 wuv = vec2(uv.x + shift, fract(uv.y + roll));

      // whale with chromatic split
      float ca = .0015 + .022*uBurst;
      vec3 col = vec3(texture2D(uWhale, wuv + vec2(ca,0.)).r,
                      texture2D(uWhale, wuv).g,
                      texture2D(uWhale, wuv - vec2(ca,0.)).b);

      // film flicker
      col *= .9 + .1*h11(fr*1.7);

      // grain / static
      float g  = h21(frag + fract(t*13.1)*1000.);
      float g2 = h21(floor(frag/2.) + fract(t*7.3)*500.);
      col += vec3(g*g) * (.05 + .2*uBurst);
      float stat = mix(g, g2, .5);
      float row  = h21(vec2(floor(frag.y/3.), floor(t*30.)));
      stat = clamp(stat + (row-.5)*.6, 0., 1.);
      col = mix(col, vec3(stat), clamp(uStatic, 0., 1.) * .97);

      // colour bars: full screen at power-on, a torn strip during glitches
      float stripY = h11(uSeed*3.1);
      float stripH = .02 + .14*h11(uSeed*5.3);
      float strip  = step(abs(uv.y - stripY), stripH) * step(.55, uBurst) * step(.5, h11(uSeed*9.7));
      float bm = max(uBars, strip*uBurst);
      vec3 bc = bars(fract(wuv.x + (uBars > .5 ? 0. : h11(uSeed)*.4)));
      col = mix(col, bc * (.75 + .35*g), bm * .9);

      // scratches: thin vertical lines that jump and break up
      for (int i = 0; i < 4; i++) {
        float fi = float(i);
        float slot = floor(t*(1.3+fi*.4) + fi*13.);
        float on   = step(.5, h11(slot*3.3+fi));
        float sx   = h11(slot+fi*7.) + (h11(fr+fi)-.5)*.002;
        float d    = abs(uv.x - sx) * uRes.x;
        float ln   = on * smoothstep(1.4, 0., d);
        ln *= step(.25, h11(floor(uv.y*(3.+fi*2.)) + fr*.37 + fi));
        float sgn = h11(slot*1.9+fi) > .35 ? 1. : -1.;
        col += sgn * ln * (.25 + .5*uBurst);
      }

      // dust and hairs
      vec2 cs = vec2(80.);
      vec2 cell = floor(frag/cs);
      float ch = h21(cell + fr*17.31);
      if (ch > .982 - .03*uBurst) {
        vec2 cp = (cell + vec2(h21(cell+fr), h21(cell*1.3+fr))) * cs;
        vec2 d = frag - cp;
        float r = 1.2 + 4.5*h21(cell+fr*2.);
        d.x *= .5 + h21(cell-fr);
        float hair = h21(cell*2.1+fr) > .85 ? 1. : 0.;
        float m = hair > .5
          ? smoothstep(1.2, 0., abs(d.y + sin(d.x*.08 + ch*20.)*8.)) * step(abs(d.x), 30.)
          : smoothstep(r, r*.4, length(d));
        col = mix(col, vec3(h21(cell*fr) > .55 ? .9 : 0.), m*.85);
      }

      // scanlines + vignette
      col *= .86 + .14*sin(frag.y*3.14159);
      col *= mix(.35, 1., smoothstep(1.05, .25, length(c*vec2(1., 1.25))));

      // bright line while the tube switches on/off
      col += vec3(1.) * (1. - smoothstep(.3, .55, uPower)) * step(.001, uPower);

      gl_FragColor = vec4(clamp(col, 0., 1.), 1.);
    }`;

  let prog, U = {}, tex;
  function initGL() {
    if (!gl) return false;
    const sh = (type, src) => {
      const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS));
    gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    for (const n of ['uRes','uTime','uStatic','uBurst','uBars','uPower','uSeed','uWhale'])
      U[n] = gl.getUniformLocation(prog, n);
    tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.uniform1i(U.uWhale, 0);
    return true;
  }

  let glOK = false;
  try { glOK = initGL(); } catch (e) { console.error('fx: WebGL failed, plain whale only', e); }
  if (!glOK) {            // fallback: show the whale canvas itself, no effects
    glc.replaceWith(wc); wc.id = 'fx';
    wc.style.width = '100%'; wc.style.height = '100%';
  }

  // ---------- whale model ----------------------------------------------------
  // Local coords: s = 0 (snout) .. 1 (fluke notch), y up, z sideways. Length 1.
  function radius(s) {
    if (s <= 0) return 0;
    if (s < .3) return .115 * Math.pow(Math.sin(s / .3 * Math.PI / 2), .55);
    const k = Math.min((s - .3) / .66, 1);
    return Math.max(.011, .115 * Math.pow(1 - k, 1.25));
  }
  function centerY(s) { return s < .3 ? -.025 * (1 - s / .3) : 0; }   // head slopes down

  const SWIM_HZ = .28;
  function undulate(s, t) {                 // vertical body wave, strongest at the tail
    return .07 * s * s * Math.sin(2 * Math.PI * (s * .75 - t * SWIM_HZ));
  }

  function bodyPt(s, th, t) {
    const r = radius(s);
    const sn = Math.sin(th);
    const y = centerY(s) + r * (sn > 0 ? 1 : .82) * sn + undulate(s, t);
    const z = r * .92 * Math.cos(th);
    return [s, y, z];
  }

  // Fluke outline (s, z), right half; mirrored for the left.
  const FLUKE = [[.95,.012],[.985,.06],[1.02,.115],[1.06,.17],[1.085,.178],[1.09,.16],
                 [1.075,.11],[1.06,.06],[1.052,.025],[1.045,0]];

  // ---------- camera / projection -------------------------------------------
  const D = 3;                              // camera distance
  let pass = null;
  let firstPass = true;
  function newPass(now) {
    // the first pass starts partway in, so the whale shows up right away
    const isFirst = firstPass;
    const head = isFirst ? 0.3 : 0;
    firstPass = false;
    const dir = Math.random() < .5 ? 1 : -1; // 1: swims right-to-left
    pass = {
      t0: now, dur: 60 + Math.random() * 25, dir,
      y: -.18 + Math.random() * .3,
      z: isFirst ? .5 : Math.random() * 1.6,
      yaw: (.25 + Math.random() * .35) * (Math.random() < .5 ? 1 : -1),
      len: .95 + Math.random() * .3,
      // ~1/3 of passes are far away and small, deep in the murk
      far: !isFirst && Math.random() < .33,
    };
    if (pass.far) { pass.z += 3; pass.len *= .8; }
    pass.t0 -= head * pass.dur * 1000;
  }

  function makeXform(t, now) {
    const p = pass;
    const k = (now - p.t0) / (p.dur * 1000);
    const span = 2.6 + p.z * .9;
    const X = p.dir * (span - 2 * span * k);
    const Y = p.y + .05 * Math.sin(t * .13) - .02 * Math.sin(t * .37);
    const Z = p.z;
    const heading = p.dir > 0 ? Math.PI : 0;   // snout points toward travel
    const yaw = heading + p.yaw;
    const pitch = .06 * Math.sin(t * .21);
    const roll = .12 * Math.sin(t * .17);
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const cr = Math.cos(roll), sr = Math.sin(roll);
    const L = p.len;
    const sc = Math.min(wc.width, wc.height * 1.9) / 2;
    return (pt) => {
      // centre the body, snout toward -x, scale to length
      let x = (pt[0] - .5) * -L, y = pt[1] * L, z = pt[2] * L;
      // roll (around x)
      let y1 = y * cr - z * sr, z1 = y * sr + z * cr;
      // pitch (around z)
      let x2 = x * cp - y1 * sp, y2 = x * sp + y1 * cp;
      // yaw (around y)
      let x3 = x2 * cy + z1 * sy, z3 = -x2 * sy + z1 * cy;
      const wxp = x3 + X, wyp = y2 + Y, wzp = z3 + Z;
      const f = D / (D + wzp);
      return [wc.width / 2 + wxp * f * sc, wc.height / 2 - wyp * f * sc, z3, f, k];
    };
  }

  // segment batching by brightness bucket (front of the body brighter)
  const NB = 5;
  const buckets = Array.from({ length: NB }, () => []);
  function seg(a, b, rr) {
    const depth = (a[2] + b[2]) * .5 / rr;               // -1 front .. +1 back
    let i = Math.floor((1 - (depth * .5 + .5)) * NB);
    i = Math.max(0, Math.min(NB - 1, i));
    buckets[i].push(a[0], a[1], b[0], b[1]);
  }

  // marine snow
  const SNOW = Array.from({ length: 140 }, () => ({
    x: Math.random(), y: Math.random(), z: Math.random(), s: Math.random(),
  }));

  function drawWhale(t, now, alpha) {
    wx.globalAlpha = 1;
    wx.fillStyle = '#000';
    wx.fillRect(0, 0, wc.width, wc.height);
    if (alpha <= 0) return;

    // particles (behind and around)
    wx.fillStyle = '#9a9aa0';
    for (const p of SNOW) {
      const yy = (p.y - t * (.004 + .01 * p.z)) % 1;
      const xx = (p.x + Math.sin(t * .1 + p.s * 6) * .01) % 1;
      wx.globalAlpha = alpha * (.08 + .25 * p.z);
      const r = .6 + p.z * 1.4;
      wx.fillRect(xx * wc.width, (yy < 0 ? yy + 1 : yy) * wc.height, r, r);
    }

    if (!pass || now - pass.t0 > pass.dur * 1000) newPass(now);
    const P = makeXform(t, now);
    const rr = .12 * pass.len;
    for (const b of buckets) b.length = 0;

    const NR = 36, NM = 20, NS = 70;
    // rings
    for (let i = 1; i <= NR; i++) {
      const s = .008 + (i / NR) * .945;
      let prev = null;
      for (let j = 0; j <= NM; j++) {
        const q = P(bodyPt(s, (j / NM) * Math.PI * 2, t));
        if (prev) seg(prev, q, rr);
        prev = q;
      }
    }
    // longitudinal lines
    for (let j = 0; j < NM; j++) {
      const th = (j / NM) * Math.PI * 2;
      let prev = null;
      for (let i = 0; i <= NS; i++) {
        const s = (i / NS) * .955;
        const q = P(bodyPt(s, th, t));
        if (prev) seg(prev, q, rr);
        prev = q;
      }
    }
    // throat grooves (dense lines on the lower jaw)
    for (let j = 0; j < 14; j++) {
      const th = Math.PI * (1.18 + j * .047);
      let prev = null;
      for (let i = 0; i <= 24; i++) {
        const s = .02 + (i / 24) * .4;
        const q = P(bodyPt(s, th, t));
        if (prev) seg(prev, q, rr);
        prev = q;
      }
    }
    // flukes
    for (const side of [1, -1]) {
      let prev = null;
      const outline = [];
      for (const [s, z] of FLUKE) {
        const lift = undulate(s, t) + (s - .95) * .5 * Math.sin(2 * Math.PI * (.75 - t * SWIM_HZ) - .6);
        const q = P([s, lift, z * side]);
        outline.push(q);
        if (prev) seg(prev, q, rr);
        prev = q;
      }
      for (let i = 1; i < 5; i++) seg(outline[i], outline[outline.length - 1 - i] || outline[0], rr);
    }
    // pectoral fins (long, humpback-style), gently flapping
    for (const side of [1, -1]) {
      const flap = .05 * Math.sin(t * .9 + (side > 0 ? 0 : .7));
      const root = [.29, -.055, .085 * side];
      const tip = [.56, -.17 + flap, .36 * side];
      const N = 12;
      const lead = [], trail = [];
      for (let i = 0; i <= N; i++) {
        const u = i / N;
        const w = .055 * (1 - u) + .012 + (i % 3 === 1 ? .006 : 0);   // bumpy leading edge
        const cx = root[0] + (tip[0] - root[0]) * u;
        const cy = root[1] + (tip[1] - root[1]) * u + flap * u * u + undulate(cx, t);
        const cz = root[2] + (tip[2] - root[2]) * u;
        lead.push(P([cx - w * .6, cy, cz]));
        trail.push(P([cx + w * .4, cy - .004, cz]));
      }
      for (let i = 0; i < N; i++) { seg(lead[i], lead[i + 1], rr); seg(trail[i], trail[i + 1], rr); }
      for (let i = 0; i <= N; i += 2) seg(lead[i], trail[i], rr);
      seg(lead[N], trail[N], rr);
    }
    // small dorsal fin
    {
      const s0 = .66, s1 = .72, s2 = .75;
      const top = (s) => radius(s) + undulate(s, t);
      const a = P([s0, top(s0), 0]), b = P([s1 - .01, top(s1) + .035, 0]), c = P([s2, top(s2), 0]);
      seg(a, b, rr); seg(b, c, rr);
    }
    // eyes
    for (const side of [1, -1]) {
      let prev = null;
      for (let j = 0; j <= 8; j++) {
        const a = j / 8 * Math.PI * 2;
        const q = P([.19 + Math.cos(a) * .008, -.035 + Math.sin(a) * .006 + undulate(.19, t), .098 * side]);
        if (prev) seg(prev, q, rr);
        prev = q;
      }
    }

    // stroke buckets
    const fade = pass.far ? .45 : 1;
    wx.lineWidth = pass.far ? .8 : 1.15;
    wx.lineCap = 'round';
    for (let i = 0; i < NB; i++) {
      const b = buckets[i];
      if (!b.length) continue;
      const lum = Math.round(70 + 170 * (i / (NB - 1)));
      wx.strokeStyle = `rgb(${lum},${lum},${lum + 6})`;
      wx.globalAlpha = alpha * fade * (.25 + .75 * (i / (NB - 1)));
      wx.beginPath();
      for (let k = 0; k < b.length; k += 4) { wx.moveTo(b[k], b[k + 1]); wx.lineTo(b[k + 2], b[k + 3]); }
      wx.stroke();
    }
    wx.globalAlpha = 1;
  }

  // ---------- timeline -------------------------------------------------------
  // Startup: black → CRT line → static + colour bars → settles to film grain.
  const ss = (a, b, x) => { const k = Math.min(Math.max((x - a) / (b - a), 0), 1); return k * k * (3 - 2 * k); };
  let burst = 0, burstUntil = 0, burstPeak = 0, seed = Math.random() * 100;
  let nextAuto = 5000;
  let power = 0, powerTarget = null, powerCb = null, powerStart = 0;
  const listeners = [];

  function triggerBurst(strength, ms) {
    const now = performance.now();
    burstPeak = Math.max(strength, now < burstUntil ? burstPeak : 0);
    burstUntil = now + ms;
    seed = Math.random() * 100;
    for (const f of listeners) f(strength, ms);
  }

  function frame(now) {
    if (!wc.width || !wc.height) {          // window not sized yet
      if (innerWidth) resize();
      requestAnimationFrame(frame);
      return;
    }
    const T = (now - START) / 1000;
    const t = T;

    // power-on, or power-off when requested
    if (powerTarget === 0) {
      power = 1 - ss(0, .55, (now - powerStart) / 1000);
      if (power <= 0.0001 && powerCb) { const cb = powerCb; powerCb = null; setTimeout(cb, 150); }
    } else {
      power = ss(.25, 1.0, T);
    }

    let stat = 1 - ss(2.7, 3.8, T);
    let bars = 0;
    if (T > 1.0 && T < 2.7) {
      // bars flicker in and out during warm-up
      const ph = Math.floor(T * 8);
      bars = (ph % 5 === 1 || ph % 5 === 2 || (T > 1.9 && T < 2.25)) ? 1 : 0;
    }

    // glitch bursts
    if (T > 3.8 && now - START > nextAuto && powerTarget !== 0) {
      triggerBurst(.35 + Math.random() * .65, 80 + Math.random() * 420);
      nextAuto = now - START + 4000 + Math.random() * 9000;
    }
    if (now < burstUntil) {
      burst = burstPeak * (.6 + .4 * Math.random());
      if (Math.random() < .3) seed = Math.random() * 100;
    } else {
      burst = Math.max(0, burst - .08);
    }
    let b = Math.max(burst, T < 3.6 ? (1 - ss(2.6, 3.6, T)) * .8 : 0);
    if (powerTarget === 0) { b = Math.max(b, .7); stat = Math.max(stat, .4 * (1 - power)); }

    const whaleAlpha = ss(2.9, 5.0, T);
    drawWhale(t, now, whaleAlpha);

    if (glOK) {
      gl.uniform2f(U.uRes, W, H);
      gl.uniform1f(U.uTime, t);
      gl.uniform1f(U.uStatic, stat);
      gl.uniform1f(U.uBurst, b);
      gl.uniform1f(U.uBars, bars);
      gl.uniform1f(U.uPower, power);
      gl.uniform1f(U.uSeed, seed);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, wc);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    } else if (powerTarget === 0 && powerCb) {
      const cb = powerCb; powerCb = null; cb();
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  window.FX = {
    burst: triggerBurst,
    onBurst: (f) => listeners.push(f),
    powerOff(cb) { powerTarget = 0; powerStart = performance.now(); powerCb = cb; },
    startedAt: START,
  };
})();
