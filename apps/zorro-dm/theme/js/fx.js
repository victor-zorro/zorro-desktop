// zorro greeter — background effects.
// A wireframe sea animal is drawn on a 2D canvas, then fed as a texture into a
// WebGL shader that adds the chaos: CRT power-on, TV static, film grain,
// dust, scratches, tearing, chromatic split and colour bars.
// Everything is configurable: window.ZORRO_LOOK (injected by zorro-greeter from
// /etc/zorro-dm/look.json, edited in the Zorro app → Look).
// Exposes window.FX = { burst(strength, ms), powerOff(cb), onBurst(fn), setLook(obj) }.
(() => {
  'use strict';

  // ---------- settings -------------------------------------------------------
  const DEFAULTS = {
    animal: 'whale',            // whale vaquita hammerhead turtle manta random
    line_colour: '#e6e6ec', density: 1, size: 1, swim_speed: 1,
    pass_seconds: 70, gap_seconds: 0, far: 0.33,
    snow_amount: 140, snow_speed: 1, snow_size: 1, snow_colour: '#9a9aa0', snow_alpha: 1,
    // defaults = the "Chromatic sea" preset (theme/presets.json)
    grain: 0.6, scratches: 0.25, dust: 0.25, scanlines: 0.6, vignette: 1, flicker: 0.3,
    chroma: 0.6, glitch_rate: 0.15, glitch_strength: 0.5, bars: false, crt: false,
    // chromatic blur: the light splits into its colours and smears like through a lens
    cblur: 1, cblur_mode: 'lens',  // lens (from the centre outward), prism (sideways), glow
    bloom: 0.6,                    // soft coloured glow around the lines
    // the iridescent background behind the animal (chromatic aberration in flowing colour)
    background: 'deep',            // deep (dark, pools of light), waves, streaks, black
    bg_strength: 1, bg_speed: 1, bg_aberration: 1,
    fps: 30,                       // the wallpaper asks for less
    fps_min: 10,                   // smart frame rate: this low while nothing moves fast
    render_scale: 1,               // < 1: draw smaller and let the screen scale it up
  };
  const BG_MODES = { waves: 0, streaks: 1, deep: 2 };
  const CBLUR_MODES = { lens: 0, prism: 1, glow: 2 };
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
    const k = DPR * Math.min(1, Math.max(0.25, +cfg.render_scale || 1));
    W = Math.floor(innerWidth * k); H = Math.floor(innerHeight * k);
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
    uniform float uCBlur, uCMode, uBloom, uBgOn, uBgStrength, uFade;
    uniform sampler2D uBg;
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

      // animal with chromatic split (sharp, grows with glitches)
      float ca = (.0015 + .022*uBurst) * uChroma;
      vec3 col = vec3(texture2D(uWhale, wuv + vec2(ca,0.)).r,
                      texture2D(uWhale, wuv).g,
                      texture2D(uWhale, wuv - vec2(ca,0.)).b);

      // chromatic blur: sample along a line, each tap tinted by its place in the
      // spectrum (red .. green .. blue), so light fans out into colour and smears
      if (uCBlur > 0.) {
        vec2 dir;
        if (uCMode < .5)      dir = (wuv - .5) * .045;                 // lens: radial
        else if (uCMode < 1.5) dir = vec2(.012, 0.);                   // prism: sideways
        else                  dir = (wuv - .5) * .02;                  // glow: softer lens
        dir *= uCBlur * (1. + 1.5*uBurst);
        vec3 acc = vec3(0.), wsum = vec3(0.);
        for (int i = 0; i < 12; i++) {
          float k = float(i) / 11.;
          vec3 w = clamp(vec3(1.6 - 2.6*k, 1. - abs(2.*k - 1.)*1.4, 2.6*k - 1.), 0., 1.) + .04;
          vec3 s = texture2D(uWhale, wuv + dir*(k - .5)).rgb;
          acc += s * w; wsum += w;
        }
        vec3 disp = acc / wsum;
        float mixk = uCMode > 1.5 ? .55 : .85;
        col = mix(col, max(col*.55, disp*1.6), clamp(uCBlur, 0., 1.) * mixk);
      }
      // the iridescent background shows through everywhere the animal is not
      if (uBgOn > .5) {
        vec3 bg = texture2D(uBg, uv).rgb * uBgStrength;
        col = 1. - (1. - col) * (1. - clamp(bg, 0., 1.));      // screen blend
      }
      // bloom: a wide, coloured glow (red outside, cyan inside)
      if (uBloom > 0.) {
        vec3 b = vec3(0.);
        for (int i = 0; i < 8; i++) {
          float a = float(i) * .785398;
          vec2 o = vec2(cos(a), sin(a));
          b.r += texture2D(uWhale, wuv + o * .009).g;
          b.g += texture2D(uWhale, wuv + o * .006).g;
          b.b += texture2D(uWhale, wuv + o * .004).g;
        }
        // red reaches widest, blue stays tight: a warm halo with a cool core
        col += b / 8. * vec3(.95, .4, .7) * uBloom * .6
             + texture2D(uWhale, wuv).g * vec3(.1, .9, 1.) * uBloom * .12;
      }

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

      gl_FragColor = vec4(clamp(col * uFade, 0., 1.), 1.);
    }`;

  // ---------- iridescent background (own program, quarter resolution) -----
  const BG_FS = `
    precision highp float;
    uniform vec2 R; uniform float T, MODE, CA;
    float h(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
    float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
      return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
    float fbm(vec2 p){float v=0.,a=.55;for(int i=0;i<3;i++){v+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.45;}return v;}
    float waves(vec2 p,float t){
      vec2 q=vec2(fbm(p+vec2(0.,t*.05)),fbm(p+vec2(5.2,1.3)-t*.04));
      vec2 r=vec2(fbm(p+3.*q+vec2(1.7,9.2)),fbm(p+3.*q+vec2(8.3,2.8)));
      return clamp((fbm(p+3.2*r)-.19)*5.,0.,1.);}          // measured range .2-.4
    float streaks(vec2 p,float t){
      return fbm(vec2(p.x*2.2+.35*sin(p.y*.9+t*.2),p.y*.10+t*.03))*1.25-.12;}
    vec3 ramp(float v,vec3 a,vec3 b,vec3 c,vec3 d,vec3 e,vec3 f){
      vec3 col=mix(a,b,smoothstep(.20,.42,v)); col=mix(col,c,smoothstep(.42,.55,v));
      col=mix(col,d,smoothstep(.55,.64,v)); col=mix(col,e,smoothstep(.64,.74,v));
      return mix(col,f,smoothstep(.74,.86,v));}
    vec3 palW(float v){return ramp(v,vec3(.0,.0,.55),vec3(.02,.05,1.),vec3(.55,.12,.95),
      vec3(1.,.38,.72),vec3(1.,.62,.25),vec3(.75,.95,1.));}
    vec3 palS(float v){return ramp(v,vec3(.03,.0,.07),vec3(.05,.08,.65),vec3(.75,.0,.75),
      vec3(.95,.0,.35),vec3(.95,.85,.88),vec3(1.,.5,.1));}
    void main(){
      vec2 p=(gl_FragCoord.xy-.5*R)/R.y;
      vec3 col;
      if(MODE>.5&&MODE<1.5){
        vec2 d=vec2(.045*CA,0.);
        col=vec3(palS(streaks(p+d,T)).r,palS(streaks(p,T)).g,palS(streaks(p-d,T)).b);
      } else {
        vec2 d=normalize(vec2(.7,.7))*.04*CA;
        float vr=waves(p+d,T),vg=waves(p,T),vb=waves(p-d,T);
        col=vec3(palW(vr).r,palW(vg).g,palW(vb).b);
        if(MODE>1.5) col*=smoothstep(.38,.8,vg)*.85;
      }
      gl_FragColor=vec4(col,1.);}`;
  let bgProg = null, bgU = {}, bgTex = null, bgFbo = null, bgW = 0, bgH = 0, bgLast = -1e9;
  let progP = -1, bgP = -1;                // attribute 'p' of each program, looked up once

  let prog, U = {}, tex, quadBuf;
  const UNIFORMS = ['uRes','uTime','uStatic','uBurst','uBars','uPower','uSeed','uWhale',
                    'uGrain','uScratch','uDust','uScan','uVig','uFlick','uChroma','uBarsOn',
                    'uCBlur','uCMode','uBloom','uBgOn','uBgStrength','uBg','uFade'];
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
    quadBuf = buf;
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    const loc = progP = gl.getAttribLocation(prog, 'p');
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
    gl.uniform1i(U.uBg, 1);
    // background program + its small render target
    bgProg = gl.createProgram();
    gl.attachShader(bgProg, sh(gl.VERTEX_SHADER, VS));
    gl.attachShader(bgProg, sh(gl.FRAGMENT_SHADER, BG_FS));
    gl.linkProgram(bgProg);
    if (!gl.getProgramParameter(bgProg, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(bgProg));
    for (const n of ['R', 'T', 'MODE', 'CA']) bgU[n] = gl.getUniformLocation(bgProg, n);
    bgP = gl.getAttribLocation(bgProg, 'p');
    bgTex = gl.createTexture();
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, bgTex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    bgFbo = gl.createFramebuffer();
    gl.activeTexture(gl.TEXTURE0);
    return true;
  }

  // render the background into its small texture (about 10 times a second)
  function drawBackground(t, now) {
    const mode = BG_MODES[cfg.background];
    if (mode === undefined || !bgProg) return false;
    const w = Math.max(64, Math.floor(W / 4)), h = Math.max(36, Math.floor(H / 4));
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, bgTex);
    if (w !== bgW || h !== bgH) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.bindFramebuffer(gl.FRAMEBUFFER, bgFbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, bgTex, 0);
      bgW = w; bgH = h; bgLast = -1e9;
    }
    if (now - bgLast > 100) {
      bgLast = now;
      gl.bindFramebuffer(gl.FRAMEBUFFER, bgFbo);
      gl.viewport(0, 0, w, h);
      gl.useProgram(bgProg);
      gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
      const loc = bgP;
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(bgU.R, w, h);
      gl.uniform1f(bgU.T, t * Math.max(0, +cfg.bg_speed) + 40);
      gl.uniform1f(bgU.MODE, mode);
      gl.uniform1f(bgU.CA, +cfg.bg_aberration);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, W, H);
      gl.useProgram(prog);
      const l2 = progP;
      gl.enableVertexAttribArray(l2);
      gl.vertexAttribPointer(l2, 2, gl.FLOAT, false, 0, 0);
    }
    gl.activeTexture(gl.TEXTURE0);
    return true;
  }

  let glOK = false;
  try { glOK = initGL(); } catch (e) { console.error('fx: WebGL failed, plain animal only', e); }
  if (!glOK) {            // fallback: show the animal canvas itself, no effects
    glc.replaceWith(wc); wc.id = 'fx';
    wc.style.width = '100%'; wc.style.height = '100%';
  }

  // ---------- animal models: js/animals.js ------------------------------------
  // the wireframe animals live in their own file; they read the same live settings (cfg)
  const MODELS = window.ZORRO_ANIMALS(cfg);

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

  // the animal's lines for this frame, projected and sorted into brightness buckets;
  // false while the water is empty
  function buildAnimal(t, now) {
    if (pass && now - pass.t0 > pass.dur * 1000) {        // the animal has gone
      pass = null;
      nextPassAt = now + Math.max(0, +cfg.gap_seconds || 0) * 1000;
    }
    if (!pass) {
      if (now < nextPassAt) return false;                  // empty water for a while
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
    return true;
  }

  // ---------- GPU scene: lines and snow drawn by WebGL into a texture --------
  // (the 2D canvas path below drew thousands of lines on the CPU and uploaded the
  //  whole picture every frame; this sends only the coordinates)
  const LVS = `attribute vec2 p; attribute vec4 c; attribute float s; varying vec4 vc;
    void main(){ vc = c; gl_PointSize = s; gl_Position = vec4(p, 0., 1.); }`;
  const LFS = `precision mediump float; varying vec4 vc;
    void main(){ gl_FragColor = vec4(vc.rgb * vc.a, vc.a); }`;
  let lineProg = null, lineBuf = null, lineL = {}, sceneTex = null, sceneFbo = null, sceneW = 0, sceneH = 0;
  let verts = new Float32Array(7 * 4096);
  function initScene() {
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
    lineProg = gl.createProgram();
    gl.attachShader(lineProg, sh(gl.VERTEX_SHADER, LVS));
    gl.attachShader(lineProg, sh(gl.FRAGMENT_SHADER, LFS));
    gl.linkProgram(lineProg);
    if (!gl.getProgramParameter(lineProg, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(lineProg));
    for (const n of ['p', 'c', 's']) lineL[n] = gl.getAttribLocation(lineProg, n);
    lineBuf = gl.createBuffer();
    sceneTex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, sceneTex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    sceneFbo = gl.createFramebuffer();
  }
  function drawSceneGL(t, now, alpha) {
    if (!lineProg) initScene();
    const w = wc.width, h = wc.height;
    gl.bindTexture(gl.TEXTURE_2D, sceneTex);
    if (w !== sceneW || h !== sceneH) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.bindFramebuffer(gl.FRAMEBUFFER, sceneFbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, sceneTex, 0);
      sceneW = w; sceneH = h;
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, sceneFbo);
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (alpha > 0) {
      let n = 0;
      const need = 7 * (SNOW.length + 2 * 64000);
      if (verts.length < need) verts = new Float32Array(need);
      const put = (x, y, r, g, b, a, s) => {           // canvas pixels -> clip space
        verts[n++] = x / w * 2 - 1; verts[n++] = 1 - y / h * 2;
        verts[n++] = r; verts[n++] = g; verts[n++] = b; verts[n++] = a; verts[n++] = s;
      };
      // marine snow as points
      const [sr, sg, sb] = hex(cfg.snow_colour).map((v) => v / 255);
      const sv = cfg.snow_speed, ssz = cfg.snow_size, sa = cfg.snow_alpha;
      for (const p of SNOW) {
        const yy = (p.y - t * (.004 + .01 * p.z) * sv) % 1;
        const xx = ((p.x + Math.sin(t * .1 + p.s * 6) * .01) % 1 + 1) % 1;
        put(xx * w, (yy < 0 ? yy + 1 : yy) * h, sr, sg, sb,
            Math.min(1, alpha * (.08 + .25 * p.z) * sa), Math.max(1, (.6 + p.z * 1.4) * ssz));
      }
      const nSnow = n / 7;
      // the animal as lines, nearer = brighter
      if (buildAnimal(t, now)) {
        const [cr, cg, cb] = hex(cfg.line_colour).map((v) => v / 255);
        const fade = pass.far ? .45 : 1;
        for (let i = 0; i < NB; i++) {
          const b = buckets[i];
          const f = (70 + 170 * (i / (NB - 1))) / 240;
          const a = alpha * fade * (.25 + .75 * (i / (NB - 1)));
          if (verts.length < n + b.length / 4 * 14 + 14) {
            const bigger = new Float32Array((n + b.length / 4 * 14) * 2); bigger.set(verts); verts = bigger;
          }
          for (let k = 0; k < b.length; k += 4) {
            put(b[k], b[k + 1], cr * f, cg * f, cb * f, a, 1);
            put(b[k + 2], b[k + 3], cr * f, cg * f, cb * f, a, 1);
          }
        }
      }
      gl.useProgram(lineProg);
      gl.bindBuffer(gl.ARRAY_BUFFER, lineBuf);
      gl.bufferData(gl.ARRAY_BUFFER, verts.subarray(0, n), gl.STREAM_DRAW);
      gl.enableVertexAttribArray(lineL.p);
      gl.enableVertexAttribArray(lineL.c);
      gl.enableVertexAttribArray(lineL.s);
      gl.vertexAttribPointer(lineL.p, 2, gl.FLOAT, false, 28, 0);
      gl.vertexAttribPointer(lineL.c, 4, gl.FLOAT, false, 28, 8);
      gl.vertexAttribPointer(lineL.s, 1, gl.FLOAT, false, 28, 24);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.drawArrays(gl.POINTS, 0, nSnow);
      if (n / 7 > nSnow) gl.drawArrays(gl.LINES, nSnow, n / 7 - nSnow);
      gl.disable(gl.BLEND);
      gl.disableVertexAttribArray(lineL.c);
      gl.disableVertexAttribArray(lineL.s);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, W, H);
    // back to the main program and its full-screen quad
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
    const l2 = progP;
    gl.enableVertexAttribArray(l2);
    gl.vertexAttribPointer(l2, 2, gl.FLOAT, false, 0, 0);
  }

  // canvas fallback (no WebGL): the same picture, drawn on the CPU
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

    if (!buildAnimal(t, now)) return;

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
    if (typeof wake === 'function') { lastFrame = 0; wake(); }
  }

  // ---------- smart frame rate -------------------------------------------------
  // Measured on the T14: the effects cost almost nothing, every frame drawn costs about
  // the same (web engine + X server + GPU). So draw fast only while something moves fast:
  // fades, glitches and the animal crossing the screen (about 3 screen px per frame);
  // empty water and an animal outside the screen get fps_min (the background itself
  // only changes ten times a second).
  const STEP_PX = 3;
  function animalFps(now) {
    const p = pass;
    if (!p || now < p.t0 || now - p.t0 > p.dur * 1000) return 0;
    const k = (now - p.t0) / (p.dur * 1000);
    const span = 2.6 + p.z * .9;
    const f = CAM / (CAM + p.z);
    const sc = Math.min(wc.width, wc.height * 1.9) / 2;
    const toScreen = innerWidth / Math.max(1, wc.width);
    const x = p.dir * (span - 2 * span * k) * f * sc;                  // animal canvas px
    if (Math.abs(x) > wc.width / 2 + p.len * f * sc) return 0;        // off the screen
    const speed = 2 * span / p.dur * f * sc * toScreen * 1.3;         // + body motion
    return speed / STEP_PX;
  }
  function wantFps(now, t) {
    const top = Math.max(1, Math.min(60, +cfg.fps || 30));
    const low = Math.min(top, Math.max(1, +cfg.fps_min || top));
    if (t < 2.5 || (cfg.crt && t < 4.5) || powerTarget === 0 || now < burstUntil + 300 || burst > .01)
      return top;
    return Math.max(low, Math.min(top, animalFps(now)));
  }

  let lastFrame = 0, paused = false, timer = 0, curFps = 0, rafPending = false;
  function raf() {                          // one frame chain only, however often woken
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame((now) => { rafPending = false; frame(now); });
  }
  function wake() { clearTimeout(timer); timer = 0; if (!paused) raf(); }
  function next(now) {                      // sleep until the next frame is due: no 60 Hz
    const fps = wantFps(now, (now - START) / 1000);  // wake-ups when drawing at 10 fps
    curFps = fps;
    const wait = Math.max(0, lastFrame + 1000 / fps - performance.now() - 4);
    clearTimeout(timer); timer = 0;
    if (wait < 8) raf();
    else timer = setTimeout(() => { timer = 0; raf(); }, wait);
  }
  function frame(now) {
    if (paused) return;                     // FX.pause(false) starts it again
    if (now - lastFrame < 1000 / wantFps(now, (now - START) / 1000) - 1) { next(now); return; }
    lastFrame = now;
    if (!wc.width || !wc.height) {          // window not sized yet
      if (innerWidth) resize();
      raf();
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

    if (!glOK) drawScene(t, now, ss(2.9, 5.0, T));

    if (glOK) {
      gl.activeTexture(gl.TEXTURE0);
      drawSceneGL(t, now, ss(2.9, 5.0, T));             // lines + snow on the GPU
      const bgOn = drawBackground(t, now);
      gl.uniform1f(U.uBgOn, bgOn ? 1 : 0);
      gl.uniform1f(U.uBgStrength, +cfg.bg_strength);
      // no TV start: a soft fade in from black over two seconds instead of static
      gl.uniform1f(U.uFade, cfg.crt ? 1 : ss(0, 2, t));
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
      gl.uniform1f(U.uCBlur, +cfg.cblur);
      gl.uniform1f(U.uCMode, CBLUR_MODES[cfg.cblur_mode] ?? 0);
      gl.uniform1f(U.uBloom, +cfg.bloom);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, sceneTex);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    } else if (powerTarget === 0 && powerCb) {
      const cb = powerCb; powerCb = null; cb();
    }
    next(now);
  }
  raf();

  window.FX = {
    burst: triggerBurst,
    onBurst: (f) => listeners.push(f),
    // the session starts from inside the frame loop: wake it even when paused (idle screen)
    powerOff(cb) { powerTarget = 0; powerStart = performance.now(); powerCb = cb; paused = false; wake(); },
    // live changes (the Zorro app's preview); a new animal swims in right away
    setLook(obj) {
      const animal = cfg.animal;
      Object.assign(cfg, obj || {});
      if (cfg.animal !== animal) { pass = null; nextPassAt = 0; firstPass = true; }
      makeSnow();
      lastFrame = 0; wake();
    },
    // the wallpaper stops drawing while windows cover it
    pause(on) {
      if (paused === !!on) return;
      paused = !!on;
      clearTimeout(timer); timer = 0;
      if (!paused) { lastFrame = 0; raf(); }
    },
    get fps() { return curFps; },
    get crt() { return !!cfg.crt; },        // the slow CRT start: the login box waits for it
    startedAt: START,
  };
})();
