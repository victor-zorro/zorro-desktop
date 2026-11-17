// zorro greeter — background effects.
// A wireframe sea animal is drawn on a 2D canvas, then fed as a texture into a
// WebGL shader that adds the chaos: CRT power-on, TV static, film grain,
// dust, scratches, tearing, chromatic split and colour bars.
// Everything is configurable: window.ZORRO_LOOK (injected by zorro-greeter from
// /etc/zorro-dm/look.json, edited in the Zorro app → Login screen).
// Exposes window.FX = { burst(strength, ms), powerOff(cb), onBurst(fn), setLook(obj) }.
(() => {
  'use strict';

  // ---------- settings -------------------------------------------------------
  const DEFAULTS = {
    animal: 'whale',            // whale vaquita hammerhead turtle manta random
    line_colour: '#e6e6ec', density: 1, size: 1, swim_speed: 1,
    pass_seconds: 70, gap_seconds: 0, far: 0.33,
    snow_amount: 140, snow_speed: 1, snow_size: 1, snow_colour: '#9a9aa0', snow_alpha: 1,
    grain: 1, scratches: 1, dust: 1, scanlines: 1, vignette: 1, flicker: 1,
    chroma: 1, glitch_rate: 1, glitch_strength: 1, bars: true, crt: true,
  };
  const cfg = Object.assign({}, DEFAULTS, window.ZORRO_LOOK || {});
  const ANIMALS = ['whale', 'vaquita', 'hammerhead', 'turtle', 'manta'];
  const hex = (h) => { const m = /^#?([0-9a-f]{6})$/i.exec(h || ''); const n = parseInt(m ? m[1] : 'e6e6ec', 16);
                       return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };

  const DPR = 1;                 // greeter runs at native res; keep it cheap
  const WHALE_SCALE = 0.75;      // animal canvas resolution vs screen
  const START = performance.now();
  const TAU = Math.PI * 2;

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
    uniform float uGrain, uScratch, uDust, uScan, uVig, uFlick, uChroma, uBarsOn;
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
      uv += vec2(h11(fr)-.5, h11(fr+3.)-.5) * .0012 * uFlick;

      // horizontal tearing in bands while glitching
      float nb    = mix(6., 48., h11(uSeed));
      float band  = floor(uv.y*nb);
      float bh    = h21(vec2(band, floor(t*18.)+uSeed));
      float shift = bh > 1. - .45*uBurst ? (h11(band*1.7+uSeed)-.5) * .3 * uBurst : 0.;
      // vertical roll while the set is warming up
      float roll  = uStatic * fract(t*.9) * .35;
      vec2 wuv = vec2(uv.x + shift, fract(uv.y + roll));

      // animal with chromatic split
      float ca = (.0015 + .022*uBurst) * uChroma;
      vec3 col = vec3(texture2D(uWhale, wuv + vec2(ca,0.)).r,
                      texture2D(uWhale, wuv).g,
                      texture2D(uWhale, wuv - vec2(ca,0.)).b);

      // film flicker
      col *= 1. - .1*uFlick*(1. - h11(fr*1.7));

      // grain / static
      float g  = h21(frag + fract(t*13.1)*1000.);
      float g2 = h21(floor(frag/2.) + fract(t*7.3)*500.);
      col += vec3(g*g) * (.05 + .2*uBurst) * uGrain;
      float stat = mix(g, g2, .5);
      float row  = h21(vec2(floor(frag.y/3.), floor(t*30.)));
      stat = clamp(stat + (row-.5)*.6, 0., 1.);
      col = mix(col, vec3(stat), clamp(uStatic, 0., 1.) * .97);

      // colour bars: full screen at power-on, a torn strip during glitches
      float stripY = h11(uSeed*3.1);
      float stripH = .02 + .14*h11(uSeed*5.3);
      float strip  = step(abs(uv.y - stripY), stripH) * step(.55, uBurst) * step(.5, h11(uSeed*9.7));
      float bm = max(uBars, strip*uBurst*uBarsOn);
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
        col += sgn * ln * (.25 + .5*uBurst) * uScratch;
      }

      // dust and hairs
      vec2 cs = vec2(80.);
      vec2 cell = floor(frag/cs);
      float ch = h21(cell + fr*17.31);
      if (uDust > 0. && ch > 1. - (.018 + .03*uBurst) * uDust) {
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
      col *= max(0., 1. - .14*uScan + .14*uScan*sin(frag.y*3.14159));
      col *= mix(max(0., 1. - .65*uVig), 1., smoothstep(1.05, .25, length(c*vec2(1., 1.25))));

      // bright line while the tube switches on/off
      col += vec3(1.) * (1. - smoothstep(.3, .55, uPower)) * step(.001, uPower);

      gl_FragColor = vec4(clamp(col, 0., 1.), 1.);
    }`;

  let prog, U = {}, tex;
  const UNIFORMS = ['uRes','uTime','uStatic','uBurst','uBars','uPower','uSeed','uWhale',
                    'uGrain','uScratch','uDust','uScan','uVig','uFlick','uChroma','uBarsOn'];
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
    for (const n of UNIFORMS) U[n] = gl.getUniformLocation(prog, n);
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
  try { glOK = initGL(); } catch (e) { console.error('fx: WebGL failed, plain animal only', e); }
  if (!glOK) {            // fallback: show the animal canvas itself, no effects
    glc.replaceWith(wc); wc.id = 'fx';
    wc.style.width = '100%'; wc.style.height = '100%';
  }

  // ---------- animal models --------------------------------------------------
  // Local coords: s = 0 (front) .. 1 (tail), y up, z sideways; length 1.
  // Each model returns { lines: [[ [s,y,z], ... ], ...] } for time t (seconds).
  const D = cfg => Math.max(.3, +cfg.density || 1);
  const n = (k) => Math.max(3, Math.round(k * D(cfg)));
  const circle = (cx, cy, cz, r, plane, steps = 10) => {     // small circle (eye etc.)
    const out = [];
    for (let j = 0; j <= steps; j++) {
      const a = j / steps * TAU, u = Math.cos(a) * r, v = Math.sin(a) * r;
      out.push(plane === 'sy' ? [cx + u, cy + v, cz] : [cx + u, cy, cz + v]);
    }
    return out;
  };

  // body of revolution: rings + lengthwise lines
  function revolve(lines, o) {
    const pt = (s, th) => {
      const r = o.r(s), sn = Math.sin(th), w = o.wave(s);
      return [s, o.cy(s) + r * (sn > 0 ? o.up : o.down) * sn + w[0], r * o.zs * Math.cos(th) + w[1]];
    };
    const NR = n(o.rings), NM = n(o.mers), NS = n(o.ns);
    for (let i = 1; i <= NR; i++) {
      const s = o.s0 + (i / NR) * (o.s1 - o.s0), ring = [];
      for (let j = 0; j <= NM; j++) ring.push(pt(s, (j / NM) * TAU));
      lines.push(ring);
    }
    for (let j = 0; j < NM; j++) {
      const th = (j / NM) * TAU, ln = [];
      for (let i = 0; i <= NS; i++) ln.push(pt(o.s0 + (i / NS) * (o.s1 - o.s0), th));
      lines.push(ln);
    }
    return pt;
  }

  // a flat fin from root to tip: leading + trailing edge and a few ribs
  function fin(lines, root, tip, w0, w1, bend, ribs = 2) {
    const N = 12, lead = [], trail = [];
    for (let i = 0; i <= N; i++) {
      const u = i / N, w = w0 * (1 - u) + w1 * u;
      const c = [root[0] + (tip[0] - root[0]) * u, root[1] + (tip[1] - root[1]) * u + bend * u * u,
                 root[2] + (tip[2] - root[2]) * u];
      lead.push([c[0] - w * .6, c[1], c[2]]);
      trail.push([c[0] + w * .4, c[1] - .004, c[2]]);
    }
    lines.push(lead, trail);
    for (let i = 0; i <= N; i += ribs) lines.push([lead[i], trail[i]]);
    lines.push([lead[N], trail[N]]);
  }

  const MODELS = {};

  // Blue whale / humpback-style: long body, throat grooves, long pectorals, flukes
  {
    const radius = (s) => {
      if (s <= 0) return 0;
      if (s < .3) return .115 * Math.pow(Math.sin(s / .3 * Math.PI / 2), .55);
      const k = Math.min((s - .3) / .66, 1);
      return Math.max(.011, .115 * Math.pow(1 - k, 1.25));
    };
    const FLUKE = [[.95,.012],[.985,.06],[1.02,.115],[1.06,.17],[1.085,.178],[1.09,.16],
                   [1.075,.11],[1.06,.06],[1.052,.025],[1.045,0]];
    MODELS.whale = (t) => {
      const hz = .28 * cfg.swim_speed;
      const und = (s) => .07 * s * s * Math.sin(TAU * (s * .75 - t * hz));
      const lines = [];
      const pt = revolve(lines, { r: radius, cy: (s) => s < .3 ? -.025 * (1 - s / .3) : 0,
        up: 1, down: .82, zs: .92, wave: (s) => [und(s), 0], s0: .008, s1: .953,
        rings: 36, mers: 20, ns: 70 });
      for (let j = 0; j < n(14); j++) {                   // throat grooves
        const th = Math.PI * (1.18 + j * .66 / n(14)), ln = [];
        for (let i = 0; i <= 24; i++) ln.push(pt(.02 + (i / 24) * .4, th));
        lines.push(ln);
      }
      for (const side of [1, -1]) {                       // flukes
        const outline = FLUKE.map(([s, z]) => [s, und(s) + (s - .95) * .5 *
          Math.sin(TAU * (.75 - t * hz) - .6), z * side]);
        lines.push(outline);
        for (let i = 1; i < 5; i++) lines.push([outline[i], outline[outline.length - 1 - i]]);
      }
      for (const side of [1, -1]) {                       // pectoral fins, gently flapping
        const flap = .05 * Math.sin(t * .9 * cfg.swim_speed + (side > 0 ? 0 : .7));
        fin(lines, [.29, -.055 + und(.29), .085 * side], [.56, -.17 + flap + und(.56), .36 * side],
            .067, .012, flap);
      }
      const top = (s) => radius(s) + und(s);              // small dorsal fin
      lines.push([[.66, top(.66), 0], [.71, top(.72) + .035, 0], [.75, top(.75), 0]]);
      for (const side of [1, -1]) lines.push(circle(.19, -.035 + und(.19), .098 * side, .008, 'sy', 8));
      return { lines };
    };
  }

  // Vaquita: the smallest, rarest porpoise; round head, tall dorsal fin, dark eye rings
  {
    const radius = (s) => s <= 0 ? 0 : s < .22 ? .13 * Math.pow(Math.sin(s / .22 * Math.PI / 2), .5)
      : Math.max(.012, .13 * Math.pow(1 - Math.min((s - .22) / .7, 1), 1.3));
    MODELS.vaquita = (t) => {
      const hz = .45 * cfg.swim_speed;
      const und = (s) => .05 * s * s * Math.sin(TAU * (s * .8 - t * hz));
      const lines = [];
      revolve(lines, { r: radius, cy: () => 0, up: 1, down: .9, zs: .95,
        wave: (s) => [und(s), 0], s0: .01, s1: .93, rings: 26, mers: 18, ns: 50 });
      const top = (s) => radius(s) + und(s);              // tall triangular dorsal fin
      const a = [.42, top(.42), 0], apex = [.52, top(.5) + .1, 0], b = [.6, top(.6), 0];
      lines.push([a, apex, b]);
      for (let i = 1; i < 4; i++) {
        const u = i / 4, base = [.42 + .18 * u, top(.42 + .18 * u), 0];
        lines.push([base, [apex[0] - (1 - u) * .03, apex[1] - .1 * (1 - u) * .5, 0]]);
      }
      for (const side of [1, -1]) {
        const flap = .03 * Math.sin(t * 1.4 * cfg.swim_speed + side);
        fin(lines, [.24, -.06 + und(.24), .08 * side], [.36, -.13 + und(.36) + flap, .18 * side], .04, .01, flap);
        const fl = [[.9,.008],[.93,.05],[.97,.1],[1.0,.13],[1.015,.12],[1.0,.07],[.99,.03],[.985,0]]
          .map(([s, z]) => [s, und(s) + (s - .9) * .5 * Math.sin(TAU * (.8 - t * hz) - .6), z * side]);
        lines.push(fl);
        lines.push(circle(.1, .012 + und(.1), .095 * side, .022, 'sy', 12));   // dark eye ring
        lines.push(circle(.1, .012 + und(.1), .097 * side, .01, 'sy', 8));
        lines.push(circle(.035, -.03 + und(.035), .07 * side, .014, 'sy', 8)); // lip patch
      }
      return { lines, scale: .75 };
    };
  }

  // Scalloped hammerhead: the wide "hammer" head, tall dorsal, sideways tail beat
  {
    const radius = (s) => s <= 0 ? 0 : s < .33 ? Math.max(.025, .085 * Math.pow(Math.sin(s / .33 * Math.PI / 2), .8))
      : Math.max(.01, .085 * Math.pow(1 - Math.min((s - .33) / .55, 1), 1.15));
    MODELS.hammerhead = (t) => {
      const hz = .5 * cfg.swim_speed;
      const und = (s) => .06 * s * s * Math.sin(TAU * (s * .9 - t * hz));
      const lines = [];
      revolve(lines, { r: radius, cy: () => 0, up: 1.05, down: .85, zs: .8,
        wave: (s) => [0, und(s)], s0: .05, s1: .88, rings: 30, mers: 16, ns: 56 });
      // the hammer (cephalofoil): a flat wing across the head, eyes at the tips
      const HW = .2, front = [], back = [];
      for (let i = 0; i <= 16; i++) {
        const z = -HW + 2 * HW * i / 16, k = z / HW;
        front.push([.015 + .03 * k * k, .004, z + und(.03)]);
        back.push([.07 + .012 * (1 - k * k), -.004, z + und(.07)]);
      }
      lines.push(front, back);
      for (let i = 0; i <= 16; i += 2) lines.push([front[i], back[i]]);
      for (const side of [1, -1]) lines.push(circle(.045, 0, side * HW + und(.045), .012, 'sy', 8));
      const top = (s) => radius(s) * 1.05;                 // tall first dorsal, swept back
      const d = [[.3, top(.3), und(.3)], [.43, top(.38) + .17, und(.43)], [.47, top(.47) + .025, und(.47)],
                 [.5, top(.5), und(.5)]];
      lines.push(d);
      for (let i = 1; i < 4; i++) {
        const s = .3 + .2 * i / 4;
        lines.push([[s, top(s), und(s)], [.43 + .02 * i / 4, top(.38) + .17 * (1 - i / 5), und(.43)]]);
      }
      lines.push([[.74, top(.74), und(.74)], [.79, top(.77) + .04, und(.79)], [.81, top(.81), und(.81)]]);
      for (const side of [1, -1])                          // pectorals, swept back and down
        fin(lines, [.27, -.04, .06 * side + und(.27)], [.42, -.13, .23 * side + und(.42)], .07, .015, 0);
      // tail: long upper lobe, short lower lobe, beats sideways with the body
      const tz = (s) => und(Math.min(s, 1.05)) * 1.2;
      const up = [[.86, .02, tz(.86)], [.98, .1, tz(.98)], [1.13, .2, tz(1.13)], [1.08, .12, tz(1.08)],
                  [1.0, .03, tz(1.0)], [.95, .0, tz(.95)]];
      const lo = [[.92, -.02, tz(.92)], [1.0, -.08, tz(1.0)], [1.04, -.11, tz(1.04)], [.98, -.03, tz(.98)]];
      lines.push(up, lo, [up[1], up[4]], [up[2], up[4]]);
      return { lines };
    };
  }

  // Leatherback sea turtle: ridged teardrop shell, long front flippers that fly
  {
    const shell = (s) => {
      if (s < .18 || s > .9) return 0;
      const k = s < .45 ? (s - .45) / .27 : (s - .45) / .45;
      return .17 * Math.sqrt(Math.max(0, 1 - k * k));
    };
    MODELS.turtle = (t) => {
      const hz = .22 * cfg.swim_speed;
      const lines = [];
      revolve(lines, { r: shell, cy: () => 0, up: .55, down: .22, zs: 1,
        wave: () => [0, 0], s0: .19, s1: .89, rings: 12, mers: 14, ns: 34 });
      for (let k = -3; k <= 3; k++) {                      // the 7 ridges on the shell
        const th = Math.PI / 2 + k * .32, ln = [];
        for (let i = 0; i <= 30; i++) {
          const s = .2 + .68 * i / 30, r = shell(s);
          ln.push([s, r * .55 * Math.sin(th) + .006, r * Math.cos(th)]);
        }
        lines.push(ln);
      }
      revolve(lines, { r: (s) => .05 * Math.sqrt(Math.max(0, 1 - ((s - .12) / .09) ** 2)),
        cy: () => .005, up: 1, down: .85, zs: .9, wave: () => [0, 0], s0: .03, s1: .2,
        rings: 6, mers: 10, ns: 8 });
      const flap = Math.sin(TAU * t * hz);                // both front flippers together
      for (const side of [1, -1]) {
        fin(lines, [.3, -.02, .13 * side], [.64, -.04 + .2 * flap, .56 * side], .1, .025, .1 * flap, 1);
        fin(lines, [.82, -.03, .07 * side], [.93, -.04 - .03 * flap, .17 * side], .05, .03, 0);
        lines.push(circle(.07, .025, .04 * side, .008, 'sy', 6));
      }
      return { lines, tilt: .35, scale: .85 };
    };
  }

  // Giant manta ray: a flying diamond with cephalic fins and a thin tail
  MODELS.manta = (t) => {
    const hz = .16 * cfg.swim_speed;
    const span = (s) => s < .38 ? .62 * Math.pow(Math.max(0, (s - .08) / .3), .8)
      : .62 * Math.pow(Math.max(0, 1 - (s - .38) / .4), 1.1);
    const y = (s, v) => {
      const a = Math.abs(v);
      return .16 * Math.pow(a, 1.5) * Math.sin(TAU * t * hz - a * 1.4) +
        .035 * (1 - v * v) * Math.max(0, 1 - Math.abs(s - .4) / .38);
    };
    const lines = [];
    const NS = n(14), NV = n(8);
    for (let i = 0; i <= NS; i++) {                       // spanwise lines
      const s = .08 + .7 * i / NS, sp = span(s), ln = [];
      for (let j = 0; j <= 20; j++) { const v = -1 + 2 * j / 20; ln.push([s, y(s, v), v * sp]); }
      lines.push(ln);
    }
    for (let j = -NV; j <= NV; j++) {                     // chordwise lines, incl. the edges
      const f = j / NV, ln = [];
      for (let i = 0; i <= 30; i++) { const s = .08 + .7 * i / 30; ln.push([s, y(s, f), f * span(s)]); }
      lines.push(ln);
    }
    for (const side of [1, -1])                           // cephalic fins (the "horns")
      lines.push([[.1, .01, .05 * side], [.03, -.01, .065 * side], [.0, -.035, .055 * side],
                  [.02, -.05, .04 * side]]);
    const tail = [];
    for (let i = 0; i <= 12; i++) {
      const s = .78 + .45 * i / 12;
      tail.push([s, .01 * Math.sin(TAU * (t * hz * 2 - i / 12)), .015 * Math.sin(TAU * (t * hz - i / 10))]);
    }
    lines.push(tail);
    return { lines, tilt: .55, scale: .9 };
  };

  // ---------- camera / projection -------------------------------------------
  const CAM = 3;                            // camera distance
  let pass = null, nextPassAt = 0, firstPass = true;
  function pickAnimal() {
    const a = cfg.animal;
    if (a === 'random') return ANIMALS[Math.floor(Math.random() * ANIMALS.length)];
    return MODELS[a] ? a : 'whale';
  }
  function newPass(now) {
    // the first pass starts partway in, so the animal shows up right away
    const isFirst = firstPass;
    const head = isFirst ? 0.3 : 0;
    firstPass = false;
    const dir = Math.random() < .5 ? 1 : -1; // 1: swims right-to-left
    const avg = Math.max(10, +cfg.pass_seconds || 70);
    pass = {
      animal: pickAnimal(),
      t0: now, dur: avg * (.85 + Math.random() * .35), dir,
      y: -.18 + Math.random() * .3,
      z: isFirst ? .5 : Math.random() * 1.6,
      yaw: (.25 + Math.random() * .35) * (Math.random() < .5 ? 1 : -1),
      len: .95 + Math.random() * .3,
      // some passes are far away and small, deep in the murk
      far: !isFirst && Math.random() < cfg.far,
    };
    if (pass.far) { pass.z += 3; pass.len *= .8; }
    pass.t0 -= head * pass.dur * 1000;
  }

  function makeXform(t, now, tilt) {
    const p = pass;
    const k = (now - p.t0) / (p.dur * 1000);
    const span = 2.6 + p.z * .9;
    const X = p.dir * (span - 2 * span * k);
    const Y = p.y + .05 * Math.sin(t * .13) - .02 * Math.sin(t * .37);
    const Z = p.z;
    const heading = p.dir > 0 ? Math.PI : 0;   // head points toward travel
    const yaw = heading + p.yaw;
    const pitch = .06 * Math.sin(t * .21);
    const roll = .12 * Math.sin(t * .17) + tilt;
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const cr = Math.cos(roll), sr = Math.sin(roll);
    const L = p.len;
    const sc = Math.min(wc.width, wc.height * 1.9) / 2;
    return (pt) => {
      let x = (pt[0] - .5) * -L, y = pt[1] * L, z = pt[2] * L;
      let y1 = y * cr - z * sr, z1 = y * sr + z * cr;           // roll (around x)
      let x2 = x * cp - y1 * sp, y2 = x * sp + y1 * cp;         // pitch (around z)
      let x3 = x2 * cy + z1 * sy, z3 = -x2 * sy + z1 * cy;      // yaw (around y)
      const wxp = x3 + X, wyp = y2 + Y, wzp = z3 + Z;
      const f = CAM / (CAM + wzp);
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
  let SNOW = [];
  function makeSnow() {
    const want = Math.max(0, Math.min(2000, Math.round(+cfg.snow_amount || 0)));
    while (SNOW.length < want) SNOW.push({ x: Math.random(), y: Math.random(), z: Math.random(), s: Math.random() });
    SNOW.length = want;
  }
  makeSnow();

  function drawScene(t, now, alpha) {
    wx.globalAlpha = 1;
    wx.fillStyle = '#000';
    wx.fillRect(0, 0, wc.width, wc.height);
    if (alpha <= 0) return;

    // particles (behind and around)
    wx.fillStyle = cfg.snow_colour;
    const sv = cfg.snow_speed, ssz = cfg.snow_size, sa = cfg.snow_alpha;
    for (const p of SNOW) {
      const yy = (p.y - t * (.004 + .01 * p.z) * sv) % 1;
      const xx = (p.x + Math.sin(t * .1 + p.s * 6) * .01) % 1;
      wx.globalAlpha = Math.min(1, alpha * (.08 + .25 * p.z) * sa);
      const r = (.6 + p.z * 1.4) * ssz;
      wx.fillRect(xx * wc.width, (yy < 0 ? yy + 1 : yy) * wc.height, r, r);
    }

    if (pass && now - pass.t0 > pass.dur * 1000) {        // the animal has gone
      pass = null;
      nextPassAt = now + Math.max(0, +cfg.gap_seconds || 0) * 1000;
    }
    if (!pass) {
      if (now < nextPassAt) return;                        // empty water for a while
      newPass(now);
    }
    const m = MODELS[pass.animal](t);
    const savedLen = pass.len;                           // per-animal scale and the size setting
    pass.len = savedLen * (m.scale || 1) * Math.max(.2, +cfg.size || 1);
    const rr = .12 * pass.len;
    const P = makeXform(t, now, m.tilt || 0);
    pass.len = savedLen;
    for (const b of buckets) b.length = 0;
    for (const ln of m.lines) {
      let prev = null;
      for (const pt of ln) { const q = P(pt); if (prev) seg(prev, q, rr); prev = q; }
    }

    // stroke buckets in the line colour, nearer = brighter
    const [cr, cg, cb] = hex(cfg.line_colour);
    const fade = pass.far ? .45 : 1;
    wx.lineWidth = pass.far ? .8 : 1.15;
    wx.lineCap = 'round';
    for (let i = 0; i < NB; i++) {
      const b = buckets[i];
      if (!b.length) continue;
      const f = (70 + 170 * (i / (NB - 1))) / 240;
      wx.strokeStyle = `rgb(${Math.round(cr * f)},${Math.round(cg * f)},${Math.round(cb * f)})`;
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
    strength *= Math.max(0, +cfg.glitch_strength);
    if (strength <= 0) return;
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
    const t = (now - START) / 1000;
    const T = cfg.crt ? t : t + 6;          // no CRT start: as if it is already warm

    // power-on, or power-off when requested
    if (powerTarget === 0) {
      power = 1 - ss(0, .55, (now - powerStart) / 1000);
      if (power <= 0.0001 && powerCb) { const cb = powerCb; powerCb = null; setTimeout(cb, 150); }
    } else {
      power = ss(.25, 1.0, T);
    }

    let stat = 1 - ss(2.7, 3.8, T);
    let bars = 0;
    if (cfg.bars && T > 1.0 && T < 2.7) {
      // bars flicker in and out during warm-up
      const ph = Math.floor(T * 8);
      bars = (ph % 5 === 1 || ph % 5 === 2 || (T > 1.9 && T < 2.25)) ? 1 : 0;
    }

    // glitch bursts
    const rate = Math.max(0, +cfg.glitch_rate);
    if (rate > 0 && T > 3.8 && now - START > nextAuto && powerTarget !== 0) {
      triggerBurst(.35 + Math.random() * .65, 80 + Math.random() * 420);
      nextAuto = now - START + (4000 + Math.random() * 9000) / rate;
    }
    if (now < burstUntil) {
      burst = burstPeak * (.6 + .4 * Math.random());
      if (Math.random() < .3) seed = Math.random() * 100;
    } else {
      burst = Math.max(0, burst - .08);
    }
    let b = Math.max(burst, T < 3.6 ? (1 - ss(2.6, 3.6, T)) * .8 : 0);
    if (powerTarget === 0) { b = Math.max(b, .7); stat = Math.max(stat, .4 * (1 - power)); }

    drawScene(t, now, ss(2.9, 5.0, T));

    if (glOK) {
      gl.uniform2f(U.uRes, W, H);
      gl.uniform1f(U.uTime, t);
      gl.uniform1f(U.uStatic, stat);
      gl.uniform1f(U.uBurst, b);
      gl.uniform1f(U.uBars, bars);
      gl.uniform1f(U.uPower, power);
      gl.uniform1f(U.uSeed, seed);
      gl.uniform1f(U.uGrain, +cfg.grain);
      gl.uniform1f(U.uScratch, +cfg.scratches);
      gl.uniform1f(U.uDust, +cfg.dust);
      gl.uniform1f(U.uScan, +cfg.scanlines);
      gl.uniform1f(U.uVig, +cfg.vignette);
      gl.uniform1f(U.uFlick, +cfg.flicker);
      gl.uniform1f(U.uChroma, +cfg.chroma);
      gl.uniform1f(U.uBarsOn, cfg.bars ? 1 : 0);
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
    // live changes (the Zorro app's preview); a new animal swims in right away
    setLook(obj) {
      const animal = cfg.animal;
      Object.assign(cfg, obj || {});
      if (cfg.animal !== animal) { pass = null; nextPassAt = 0; firstPass = true; }
      makeSnow();
    },
    startedAt: START,
  };
})();
