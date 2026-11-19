// The wireframe sea animals of the login / lock screen and the wallpaper (used by fx.js).
// window.ZORRO_ANIMALS(cfg) returns { name: (t, cfg) => { lines, tilt, scale } }; cfg is fx.js's
// live settings object (density is read from it while drawing).
window.ZORRO_ANIMALS = function (cfg) {
  'use strict';
  const TAU = Math.PI * 2;
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
    const zs = typeof o.zs === 'function' ? o.zs : () => o.zs;   // a number or per s (wide heads)
    const pt = (s, th) => {
      const r = o.r(s), sn = Math.sin(th), w = o.wave(s);
      return [s, o.cy(s) + r * (sn > 0 ? o.up : o.down) * sn + w[0], r * zs(s) * Math.cos(th) + w[1]];
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

  // a smooth curve through points (Catmull-Rom), u = 0..1 -> [s, y, z]
  function spline(P) {
    return (u) => {
      const f = Math.min(.9999, Math.max(0, u)) * (P.length - 1), i = Math.floor(f), k = f - i;
      const p0 = P[Math.max(0, i - 1)], p1 = P[i], p2 = P[i + 1], p3 = P[Math.min(P.length - 1, i + 2)];
      return p1.map((_, d) => .5 * (2 * p1[d] + (-p0[d] + p2[d]) * k + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * k * k +
        (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * k * k * k));
    };
  }

  // a tube along a curve C(u) in the s-y plane, radius R(u): rings + lengthwise lines
  // (for animals that are not a straight body: the seahorse); th = pi/2 is the curve's left side
  function tube(lines, C, R, o) {
    const nrm = (u) => {
      const a = C(u - .002), b = C(u + .002), ds = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(ds, dy) || 1;
      return [-dy / l, ds / l];
    };
    const pt = (u, th) => {
      const c = C(u), q = nrm(u), r = R(u), sn = Math.sin(th);
      return [c[0] + q[0] * r * sn, c[1] + q[1] * r * sn, c[2] + r * (o.zs || 1) * Math.cos(th)];
    };
    const NR = n(o.rings), NM = n(o.mers), NS = n(o.ns);
    for (let i = 0; i <= NR; i++) {
      const u = o.u0 + (i / NR) * (o.u1 - o.u0), ring = [];
      for (let j = 0; j <= NM; j++) ring.push(pt(u, (j / NM) * TAU));
      lines.push(ring);
    }
    for (let j = 0; j < NM; j++) {
      const th = (j / NM) * TAU, ln = [];
      for (let i = 0; i <= NS; i++) ln.push(pt(o.u0 + (i / NS) * (o.u1 - o.u0), th));
      lines.push(ln);
    }
    return pt;
  }

  const MODELS = {};

  // Blue whale: the longest, slender body, broad U-shaped flat head, long throat grooves,
  // short pectorals and a tiny dorsal fin far back ('whale' is the old name, kept as an alias)
  {
    const radius = (s) => {
      if (s <= 0) return 0;
      if (s < .27) return .09 * Math.pow(Math.sin(s / .27 * Math.PI / 2), .42);
      const k = Math.min((s - .27) / .68, 1);
      return Math.max(.009, .09 * Math.pow(1 - k, 1.35));
    };
    const FLUKE = [[.95,.01],[.985,.05],[1.02,.1],[1.06,.15],[1.085,.158],[1.09,.14],
                   [1.075,.1],[1.06,.055],[1.052,.022],[1.045,0]];
    MODELS.bluewhale = (t) => {
      const hz = .24 * cfg.swim_speed;
      const und = (s) => .06 * s * s * Math.sin(TAU * (s * .75 - t * hz));
      const lines = [];
      const pt = revolve(lines, { r: radius, cy: (s) => s < .27 ? -.02 * (1 - s / .27) : 0,
        up: .8, down: .85, zs: (s) => s < .25 ? 1.32 - .37 * s / .25 : .95,
        wave: (s) => [und(s), 0], s0: .008, s1: .953, rings: 38, mers: 20, ns: 74 });
      for (let j = 0; j < n(14); j++) {                   // throat grooves, back to the navel
        const th = Math.PI * (1.18 + j * .66 / n(14)), ln = [];
        for (let i = 0; i <= 26; i++) ln.push(pt(.02 + (i / 26) * .46, th));
        lines.push(ln);
      }
      for (const side of [1, -1]) {                       // flukes
        const outline = FLUKE.map(([s, z]) => [s, und(s) + (s - .95) * .5 *
          Math.sin(TAU * (.75 - t * hz) - .6), z * side]);
        lines.push(outline);
        for (let i = 1; i < 5; i++) lines.push([outline[i], outline[outline.length - 1 - i]]);
      }
      for (const side of [1, -1]) {                       // short, slim pectoral fins
        const flap = .03 * Math.sin(t * .8 * cfg.swim_speed + (side > 0 ? 0 : .7));
        fin(lines, [.27, -.05 + und(.27), .075 * side], [.41, -.12 + flap + und(.41), .21 * side],
            .04, .008, flap);
      }
      const top = (s) => radius(s) * .8 + und(s);         // the tiny dorsal fin, far back
      lines.push([[.775, top(.775), 0], [.805, top(.8) + .022, 0], [.815, top(.815), 0]]);
      for (const side of [1, -1]) lines.push(circle(.2, -.03 + und(.2), .085 * side, .007, 'sy', 8));
      lines.push([pt(.115, Math.PI * .44), pt(.15, Math.PI / 2), pt(.115, Math.PI * .56)]);   // splash guard
      return { lines, scale: 1.05 };
    };
    MODELS.whale = MODELS.bluewhale;
  }

  // North Atlantic right whale: stocky, no dorsal fin, a big head with a high arched mouth line,
  // pale callosities on the head, broad paddle flippers, wide smooth flukes
  {
    const radius = (s) => {
      if (s <= 0) return 0;
      if (s < .4) return .14 * Math.pow(Math.sin(s / .4 * Math.PI / 2), .5);
      const k = Math.min((s - .4) / .55, 1);
      return Math.max(.012, .14 * Math.pow(1 - k, 1.45));
    };
    const FLUKE = [[.94,.012],[.97,.06],[1.0,.12],[1.04,.19],[1.07,.215],[1.08,.2],
                   [1.07,.14],[1.06,.08],[1.05,.035],[1.045,0]];
    // callosity patches: [s, angle around the body (pi/2 = top), size]
    const CALL = [[.03,1.57,.02],[.075,1.4,.014],[.08,1.78,.014],[.12,1.57,.012],
                  [.14,1.05,.014],[.14,2.1,.014],[.26,.75,.016],[.26,2.4,.016]];
    MODELS.rightwhale = (t) => {
      const hz = .2 * cfg.swim_speed;
      const und = (s) => .055 * s * s * Math.sin(TAU * (s * .7 - t * hz));
      const lines = [];
      const pt = revolve(lines, { r: radius, cy: (s) => s < .3 ? .02 * (1 - s / .3) : 0,
        up: 1, down: .9, zs: .9, wave: (s) => [und(s), 0], s0: .01, s1: .945,
        rings: 32, mers: 20, ns: 64 });
      for (const side of [1, -1]) {
        for (const dl of [0, -.16]) {                     // the high arched mouth line + lower lip
          const ln = [];
          for (let i = 0; i <= 30; i++) {
            const u = i / 30, s = .012 + .29 * u;
            const th = -.2 + 1.25 * Math.sin(Math.PI * Math.pow(u, .75)) - .3 * u + dl * Math.sin(Math.PI * u);
            ln.push(pt(s, side > 0 ? th : Math.PI - th));
          }
          lines.push(ln);
        }
        lines.push(circle(.29, -.01 + und(.29), .118 * side, .008, 'sy', 8));   // eye
        const flap = .03 * Math.sin(t * .8 * cfg.swim_speed + (side > 0 ? 0 : .7));
        fin(lines, [.34, -.08 + und(.34), .11 * side], [.47, -.2 + flap + und(.47), .29 * side],
            .085, .06, flap);                             // broad paddle flippers
        const outline = FLUKE.map(([s, z]) => [s, und(s) + (s - .94) * .5 *
          Math.sin(TAU * (.7 - t * hz) - .6), z * side]);
        lines.push(outline);
        for (let i = 1; i < 5; i++) lines.push([outline[i], outline[outline.length - 1 - i]]);
      }
      for (const [s, th, r] of CALL)                      // callosities: rough raised patches
        for (const k of [1, .5]) {
          const ln = [];
          for (let j = 0; j <= 10; j++) {
            const a = j / 10 * TAU, rr = r * k * (1 + .3 * Math.sin(a * 3 + s * 40));
            const p = pt(s + Math.cos(a) * rr, th + Math.sin(a) * rr * 1.3 / Math.max(.03, radius(s)));
            ln.push([p[0], (p[1] - und(s)) * 1.06 + und(s), p[2] * 1.06]);
          }
          lines.push(ln);
        }
      return { lines, scale: .9 };
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

  // Whale shark: the biggest fish; a wide flat head with a broad mouth right at the front,
  // ridges along the back, pale spots, a tall crescent tail swept slowly side to side
  {
    const radius = (s) => s <= 0 ? 0 : s < .3 ? Math.max(.035, .115 * Math.pow(Math.sin(s / .3 * Math.PI / 2), .32))
      : Math.max(.014, .115 * Math.pow(1 - Math.min((s - .3) / .6, 1), 1.05));
    const zs = (s) => s < .28 ? 1.6 - .62 * s / .28 : .98;
    const SPOTS = [];                                     // a fixed scatter of spots on back and flanks
    for (let i = 0; i < 13; i++)
      for (let j = 0; j < 7; j++) {
        const s = .12 + i * .05 + .02 * Math.sin(j * 2.3 + i), th = .35 + j * .4 + .12 * Math.sin(i * 1.7);
        if (s < .78) SPOTS.push([s, th]);
      }
    MODELS.whaleshark = (t) => {
      const hz = .2 * cfg.swim_speed;
      const und = (s) => .06 * s * s * Math.sin(TAU * (s * .8 - t * hz));
      const lines = [];
      const pt = revolve(lines, { r: radius, cy: () => 0, up: .78, down: .62, zs,
        wave: (s) => [0, und(s)], s0: .012, s1: .9, rings: 30, mers: 14, ns: 60 });
      const raised = (s, th, k) => { const p = pt(s, th); return [p[0], p[1] * k, (p[2] - und(s)) * k + und(s)]; };
      for (const th of [.75, 1.15, 1.57, 1.99, 2.39]) {  // the ridges along the back
        const ln = [];
        for (let i = 0; i <= 30; i++) ln.push(raised(.1 + .72 * i / 30, th, 1.07));
        lines.push(ln);
      }
      for (const [s, th] of SPOTS)                        // spots
        lines.push(circle(0, 0, 0, 1, 'sy', 6).map(([u, v]) => raised(s + u * .007, th + v * .007 / radius(s), 1.03)));
      const W = radius(.016) * zs(.016), lip = [], jaw = [];          // the broad mouth at the front
      for (let i = 0; i <= 16; i++) {
        const k = -1 + 2 * i / 16, z = k * W * .9;
        lip.push([.012 + .035 * k * k, -.012, z + und(.02)]);
        jaw.push([.022 + .03 * k * k, -.03, z * .9 + und(.03)]);
      }
      lines.push(lip, jaw);
      for (const side of [1, -1]) {
        lines.push(circle(.045, .01, side * W * .95 + und(.045), .008, 'sy', 8));   // small eye
        for (let g = 0; g < 5; g++) {                     // gill slits
          const s = .19 + g * .02, ln = [];
          for (let i = 0; i <= 6; i++) ln.push(pt(s, (side > 0 ? 0 : Math.PI) + side * (-.55 + i * .17)));
          lines.push(ln);
        }
        fin(lines, [.27, -.05, .1 * side + und(.27)], [.46, -.15, .34 * side + und(.46)], .075, .015, 0);
        fin(lines, [.66, -.035, .03 * side + und(.66)], [.72, -.07, .07 * side + und(.72)], .03, .01, 0);
      }
      const top = (s) => radius(s) * .78;                // first and second dorsal fins
      const d = [[.44, top(.44), und(.44)], [.55, top(.5) + .12, und(.55)], [.58, top(.58) + .02, und(.58)],
                 [.6, top(.6), und(.6)]];
      lines.push(d);
      for (let i = 1; i < 4; i++) {
        const s = .44 + .16 * i / 4;
        lines.push([[s, top(s), und(s)], [.55 + .02 * i / 4, top(.5) + .12 * (1 - i / 5), und(.55)]]);
      }
      lines.push([[.73, top(.73), und(.73)], [.77, top(.75) + .04, und(.77)], [.78, top(.78), und(.78)]]);
      // the tall crescent tail: big upper lobe, a slightly smaller lower lobe
      const tz = (s) => und(Math.min(s, 1.05)) * 1.2;
      const up = [[.88, .016, tz(.88)], [.95, .08, tz(.95)], [1.04, .18, tz(1.04)], [1.02, .11, tz(1.02)],
                  [.98, .04, tz(.98)], [.95, 0, tz(.95)]];
      const lo = [[.95, 0, tz(.95)], [.98, -.05, tz(.98)], [1.02, -.12, tz(1.02)], [.97, -.04, tz(.97)], [.9, -.014, tz(.9)]];
      lines.push(up, lo, [up[1], up[4]], [up[2], up[4]], [lo[2], lo[0]]);
      return { lines, tilt: .25, scale: 1.1 };
    };
  }

  // Smalltooth sawfish: a ray with a shark's body, flat head and wide pectorals, and the long
  // flat saw (rostrum) in front, teeth along both edges
  {
    const SB = .3;                                        // where the body starts behind the saw
    const radius = (s) => s <= SB ? 0 : s < .52 ? Math.max(.022, .075 * Math.pow(Math.sin((s - SB) / .22 * Math.PI / 2), .6))
      : Math.max(.009, .075 * Math.pow(1 - Math.min((s - .52) / .42, 1), 1.05));
    const zs = (s) => s < .55 ? 1.75 - .75 * Math.max(0, s - SB) / .25 : 1;
    MODELS.sawfish = (t) => {
      const hz = .42 * cfg.swim_speed;
      const und = (s) => .07 * Math.pow(Math.max(0, s - SB) / .7, 2) * Math.sin(TAU * ((s - SB) * .9 - t * hz));
      const lines = [];
      revolve(lines, { r: radius, cy: () => 0, up: .72, down: .45, zs,
        wave: (s) => [0, und(s)], s0: SB + .005, s1: .93, rings: 28, mers: 14, ns: 54 });
      // the saw: a long flat blade, slightly narrowing, teeth as short ticks along both edges
      const hw = (s) => .022 + .012 * s / SB, edge = [[], []], mid = [];
      for (let i = 0; i <= 20; i++) {
        const s = SB + .01 - (SB + .01) * i / 20;
        edge[0].push([s, -.004, hw(s)]); edge[1].push([s, -.004, -hw(s)]); mid.push([s, .003, 0]);
      }
      lines.push(edge[0], edge[1], mid, [edge[0][20], edge[1][20]]);
      for (let i = 0; i < 22; i++) {
        const s = .012 + (SB - .03) * i / 21;
        for (const side of [1, -1]) lines.push([[s, -.004, side * hw(s)], [s + .007, -.004, side * (hw(s) + .022)]]);
      }
      for (const side of [1, -1]) {
        lines.push(circle(SB + .04, .03, .035 * side, .007, 'sz', 8));            // eyes on top
        // wide, ray-like pectoral fins and small pelvics
        fin(lines, [SB + .07, -.015, .07 * side + und(SB + .07)], [.5, -.04, .25 * side + und(.5)], .14, .03, 0);
        fin(lines, [.6, -.03, .04 * side + und(.6)], [.66, -.05, .11 * side + und(.66)], .04, .015, 0);
      }
      const top = (s) => radius(s) * .72;                 // two tall dorsal fins of the same shape
      for (const [a, b, h] of [[.5, .6, .1], [.72, .8, .08]]) {
        const ap = [a + (b - a) * .7, top(a) + h, und(a + (b - a) * .7)];
        lines.push([[a, top(a), und(a)], ap, [b, top(b) + .01, und(b)], [b + .01, top(b + .01), und(b + .01)]]);
        for (let i = 1; i < 3; i++) lines.push([[a + (b - a) * i / 3, top(a + (b - a) * i / 3), und(a + (b - a) * i / 3)], ap]);
      }
      const tz = (s) => und(Math.min(s, 1.05)) * 1.2;     // shark tail, long upper lobe
      const up = [[.9, .015, tz(.9)], [.97, .06, tz(.97)], [1.05, .11, tz(1.05)], [1.03, .06, tz(1.03)],
                  [1.0, .015, tz(1.0)], [.96, -.005, tz(.96)]];
      const lo = [[.95, -.01, tz(.95)], [1.0, -.05, tz(1.0)], [1.02, -.06, tz(1.02)], [.99, -.015, tz(.99)]];
      lines.push(up, lo, [up[1], up[4]], [up[2], up[4]]);
      return { lines, tilt: .5, scale: 1.05 };
    };
  }

  // Dugong: the sea cow; a round body, a heavy downturned snout, small paddle flippers,
  // a whale-like fluked tail, a slow calm glide
  {
    const body = (s) => s <= 0 ? 0 : s < .36 ? Math.max(.05, .12 * Math.pow(Math.sin(s / .36 * Math.PI / 2), .72))
      : s < .52 ? .12 : Math.max(.013, .12 * Math.pow(1 - Math.min((s - .52) / .38, 1), 1.5));
    const radius = (s) => body(s) * (1 - .14 * Math.exp(-(((s - .16) / .04) ** 2)));   // a soft neck crease
    const FLUKE = [[.9,.012],[.93,.05],[.97,.1],[1.0,.15],[1.015,.16],[1.02,.15],
                   [1.01,.11],[1.005,.06],[1.0,.02],[.995,0]];
    MODELS.dugong = (t) => {
      const hz = .17 * cfg.swim_speed;
      const und = (s) => .05 * s * s * Math.sin(TAU * (s * .7 - t * hz));
      const lines = [];
      const pt = revolve(lines, { r: radius, cy: (s) => s < .18 ? -.05 * Math.pow(1 - s / .18, 1.6) : 0,
        up: 1, down: .9, zs: 1, wave: (s) => [und(s), 0], s0: .015, s1: .905, rings: 28, mers: 18, ns: 54 });
      // the broad snout disc, facing down and forward, with a split lip
      const disc = [];
      for (let j = 0; j <= 16; j++) {
        const a = j / 16 * TAU;
        disc.push([.03 + .02 * Math.cos(a), -.075 + .012 * Math.cos(a) + und(.03), .045 * Math.sin(a)]);
      }
      lines.push(disc, [[.012, -.065, 0], [.05, -.085, 0]]);
      for (const side of [1, -1]) {
        lines.push(circle(.1, -.005 + und(.1), .06 * side, .007, 'sy', 8));       // small eye
        const flap = .04 * Math.sin(t * .7 * cfg.swim_speed + (side > 0 ? 0 : 1.2));
        fin(lines, [.2, -.06 + und(.2), .09 * side], [.31, -.13 + flap + und(.31), .22 * side], .055, .04, flap);
        const outline = FLUKE.map(([s, z]) => [s, und(s) + (s - .9) * .5 *
          Math.sin(TAU * (.7 - t * hz) - .6), z * side]);
        lines.push(outline);
        for (let i = 1; i < 5; i++) lines.push([outline[i], outline[outline.length - 1 - i]]);
      }
      return { lines, tilt: .3, scale: .8 };
    };
  }

  // Seahorse: upright, a curled tail, a long snout on a horse's head; it drifts and bobs
  // upright, a small dorsal fin fluttering on its back
  {
    const BODY = spline([[.5, .4, 0], [.535, .3, 0], [.515, .17, 0], [.455, .06, 0], [.44, -.06, 0],
      [.49, -.16, 0], [.55, -.25, 0], [.575, -.35, 0], [.555, -.44, 0], [.5, -.475, 0], [.455, -.44, 0],
      [.46, -.385, 0], [.5, -.385, 0], [.51, -.415, 0]]);
    const bodyR = (u) => u < .05 ? .03 + .4 * u : u < .4 ? .05 + .032 * Math.sin((u - .05) / .35 * Math.PI)
      : Math.max(.006, .05 * Math.pow(1 - (u - .4) / .6, 1.4));
    const HEAD = spline([[.5, .425, 0], [.45, .395, 0], [.39, .37, 0], [.32, .345, 0], [.25, .33, 0]]);
    const headR = (u) => u < .45 ? .03 + .022 * Math.sin(Math.min(1, (u + .12) / .5) * Math.PI) : u < .95 ? .014 : .018;
    MODELS.seahorse = (t) => {
      const sp = cfg.swim_speed;
      const lines = [];
      const pt = tube(lines, BODY, bodyR, { u0: 0, u1: 1, rings: 40, mers: 10, ns: 60 });
      tube(lines, HEAD, headR, { u0: 0, u1: 1, rings: 14, mers: 10, ns: 18 });
      for (const side of [1, -1]) {
        lines.push(circle(.43, .395, .04 * side, .011, 'sy', 10));                // eye
        // pectoral fin behind the eye, a quick flutter
        const base = [.47, .345, .035 * side], ln = [base];
        for (let i = 0; i <= 4; i++) {
          const a = -.9 + i * .4, f = .012 * Math.sin(t * 5 * sp + i * .8);
          ln.push([base[0] + .035 * Math.cos(a), base[1] + .035 * Math.sin(a), base[2] + side * (.02 + f)]);
        }
        lines.push(ln, [ln[ln.length - 1], base]);
      }
      lines.push([[.49, .45, 0], [.5, .49, 0], [.515, .465, 0], [.525, .485, 0], [.53, .44, 0]]);   // coronet
      // the dorsal fin on the back: a fan of rays waving like a ribbon
      const rays = [];
      for (let i = 0; i <= 8; i++) {
        const u = .33 + .13 * i / 8, b = pt(u, Math.PI / 2), f = .018 * Math.sin(t * 4.5 * sp - i * .9);
        const tip = [b[0] + .055 * Math.sin(Math.PI * (i + .5) / 9.5) + .01, b[1] - .012, b[2] + f];
        lines.push([b, tip]);
        rays.push(tip);
      }
      lines.push(rays);
      // upright: bob up and down, lean a little, no fish-like wave
      const dy = .025 * Math.sin(t * .8 * sp), lean = .06 * Math.sin(t * .45 * sp);
      const out = lines.map((ln) => ln.map(([s, y, z]) => [.5 + (s - .5) * Math.cos(lean) - y * Math.sin(lean),
        (s - .5) * Math.sin(lean) + y * Math.cos(lean) + dy, z]));
      return { lines: out, scale: .56 };
    };
  }

  // Hawksbill sea turtle: an oval shell of overlapping scute plates with a saw-toothed rear edge,
  // a narrow head with a sharp hooked beak, clawed front flippers
  {
    const S0 = .2, S1 = .84;                              // shell from .. to
    const half = (s) => {                                 // half width of the shell, pointed at the back
      if (s <= S0 || s >= S1) return 0;
      const k = s < .44 ? (s - .44) / (.44 - S0) : (s - .44) / (S1 - .44);
      return .15 * Math.pow(Math.max(0, 1 - k * k), s < .44 ? .5 : .62);
    };
    // a point on the shell: v = -1 .. 1 across, lifted a little so the plates sit on the dome
    const sh = (s, v, lift = 0) => {
      const w = half(s), vv = Math.max(-1, Math.min(1, v));
      return [s, .5 * w * Math.sqrt(1 - vv * vv) * (1 + lift) + .004, vv * w * (1 + lift * .3)];
    };
    const curve = (f, N = 14) => { const ln = []; for (let i = 0; i <= N; i++) ln.push(f(i / N)); return ln; };
    MODELS.hawksbill = (t) => {
      const hz = .24 * cfg.swim_speed;
      const lines = [];
      // the underside (plastron): a few cross lines and lengthwise lines; the dome carries the plates
      const under = (s, v) => [s, -.2 * half(s) * Math.sqrt(Math.max(0, 1 - v * v)), v * half(s)];
      for (let i = 1; i < 8; i++) { const s = S0 + (S1 - S0) * i / 8; lines.push(curve((u) => under(s, -1 + 2 * u), 12)); }
      for (const v of [-.6, -.2, .2, .6]) lines.push(curve((u) => under(S0 + .01 + (S1 - S0 - .02) * u, v), 24));
      const VB = [.24, .355, .47, .59, .7, .8];           // vertebral scutes (the middle row)
      const vw = (s) => .3 * Math.min(1, half(s) / .1);   // their half width (v)
      for (let i = 0; i < VB.length - 1; i++) {
        const a = VB[i], b = VB[i + 1];                   // six-sided plate, back edge bowed (overlap)
        for (const side of [1, -1]) lines.push(curve((u) => {
          const s = a + (b - a) * u; return sh(s, side * vw(s) * (.75 + .35 * Math.sin(Math.PI * u)), .04);
        }, 8));
        lines.push(curve((u) => { const v = -1 + 2 * u; return sh(b + .018 * (1 - v * v), v * vw(b), .05); }, 8));
      }
      lines.push(curve((u) => sh(VB[0], (-1 + 2 * u) * vw(VB[0]), .04), 6));
      const CB = [.25, .39, .55, .7, .82];                // costal scutes (4 each side)
      for (const side of [1, -1]) {
        for (let i = 1; i < CB.length - 1; i++)
          lines.push(curve((u) => {
            const s0 = VB[i] + .01, s = s0 + (CB[i] - s0) * u + .02 * Math.sin(Math.PI * u);
            return sh(s, side * (vw(s0) + (.84 - vw(s0)) * u), .045);
          }, 10));
        lines.push(curve((u) => sh(.23 + .6 * u, side * .86, .03), 24));     // inner edge of the margin
        for (let i = 0; i <= 11; i++) {                   // marginal plates
          const s = .23 + .58 * i / 11;
          lines.push([sh(s, side * .86, .03), sh(s + .012, side, 0)]);
        }
        const rim = [];                                   // the rim, saw-toothed at the back
        for (let i = 0; i <= 30; i++) {
          const s = .21 + .62 * i / 30, p = sh(s, side, 0);
          const tooth = s > .62 && i % 2 ? .02 : 0;
          rim.push([p[0] + tooth * .6, p[1], p[2] + side * tooth * .5]);
        }
        lines.push(rim);
      }
      // the head: narrow, tapering to a sharp hooked beak
      const hr = (s) => s < .1 ? .045 * Math.pow(Math.max(0, (s - .01) / .09), .7) : .045 * Math.sqrt(Math.max(0, 1 - ((s - .1) / .11) ** 2));
      revolve(lines, { r: hr, cy: (s) => s < .1 ? .01 * (1 - s / .1) : 0, up: 1, down: .8, zs: .8,
        wave: () => [0, 0], s0: .01, s1: .21, rings: 8, mers: 10, ns: 12 });
      lines.push([[.07, .045, 0], [.03, .035, 0], [.0, .02, 0], [-.016, -.002, 0], [-.01, -.022, 0], [.004, -.016, 0]]);   // the hooked beak
      const flap = Math.sin(TAU * t * hz);
      for (const side of [1, -1]) {
        lines.push([[-.006, -.012, 0], [.035, -.012, .022 * side], [.07, -.006, .03 * side]]);   // jaw line
        lines.push(circle(.065, .018, .028 * side, .008, 'sy', 8));
        lines.push(curve((u) => [.07 + .05 * u, .036 - .006 * u, side * (.012 + .02 * u)], 4)); // head scales
        // front flippers, shorter than the leatherback's, two claws on the leading edge
        fin(lines, [.3, -.02, .13 * side], [.56, -.04 + .17 * flap, .45 * side], .09, .022, .09 * flap, 1);
        for (const u of [.3, .48]) {                      // claws on the leading edge
          const w = .09 * (1 - u) + .022 * u, s = .3 + .26 * u - w * .6;
          const y = -.02 + (-.02 + .17 * flap) * u + .09 * flap * u * u, z = (.13 + .32 * u) * side;
          lines.push([[s, y, z], [s - .022, y - .004, z - .01 * side]]);
        }
        fin(lines, [.8, -.025, .07 * side], [.9, -.035 - .03 * flap, .17 * side], .05, .03, 0);
      }
      return { lines, tilt: .45, scale: .85 };
    };
  }

  // Sea otter: floats and swims on its back, paws folded on the chest, head up, hind feet and
  // a flat tail paddling behind; a few tufts and whiskers for the fur
  {
    const radius = (s) => s < .14 || s > .84 ? 0 : Math.max(s < .3 ? .05 : 0, .085 * Math.pow(Math.sin((s - .14) / .7 * Math.PI), .33));
    const cy = (s) => s < .32 ? .07 * ((.32 - s) / .18) ** 2 : .025 * ((s - .32) / .52) ** 2;  // chest and head up
    MODELS.otter = (t) => {
      const sp = cfg.swim_speed;
      const swell = (s) => .015 * Math.sin(TAU * (.13 * t * sp - s * .6));    // riding the swell
      const lines = [];
      const pt = revolve(lines, { r: radius, cy, up: .85, down: 1, zs: 1.05,
        wave: (s) => [swell(s), 0], s0: .145, s1: .835, rings: 22, mers: 14, ns: 42 });
      // head: round, raised above the chest, the face looking up and ahead
      const hc = [.085, .12], HR = .065;
      const hr = (s) => HR * Math.sqrt(Math.max(0, 1 - ((s - hc[0]) / HR) ** 2));
      revolve(lines, { r: hr, cy: () => hc[1], up: 1, down: 1, zs: 1, wave: (s) => [swell(s), 0],
        s0: hc[0] - HR + .004, s1: hc[0] + HR - .004, rings: 9, mers: 12, ns: 12 });
      const mr = (s) => .03 * Math.sqrt(Math.max(0, 1 - ((s - .035) / .032) ** 2));    // muzzle
      revolve(lines, { r: mr, cy: () => hc[1] + .03, up: .8, down: .8, zs: 1.2, wave: (s) => [swell(s), 0],
        s0: .006, s1: .064, rings: 4, mers: 10, ns: 6 });
      const sw = swell(.08);
      lines.push([[.02, hc[1] + .062 + sw, -.01], [.015, hc[1] + .068 + sw, 0], [.02, hc[1] + .062 + sw, .01],
                  [.025, hc[1] + .058 + sw, 0], [.02, hc[1] + .062 + sw, -.01]]);    // nose
      for (const side of [1, -1]) {
        lines.push(circle(.07, hc[1] + .055 + sw, .025 * side, .007, 'sz', 8));      // eyes, facing up
        lines.push(circle(.115, hc[1] + .035 + sw, .052 * side, .011, 'sy', 8));         // small round ears
        for (let w = 0; w < 3; w++)                                                 // whiskers
          lines.push([[.03, hc[1] + .045 + sw, .022 * side], [.015 - .01 * w, hc[1] + .055 - .012 * w + sw, .08 * side]]);
        for (let k = 0; k < 3; k++) {                                               // cheek tufts
          const a = -.6 + k * .5;
          lines.push([[.095 + .02 * Math.cos(a), hc[1] - .03 + sw, side * (.055 + .01 * k)],
                      [.11 + .025 * Math.cos(a), hc[1] - .045 + sw, side * (.07 + .008 * k)]]);
        }
        // forearms folded up onto the chest, the paws together on top
        const sh = pt(.22, side > 0 ? .25 : Math.PI - .25), paw = [.27, cy(.27) + radius(.27) * .85 + .025 + swell(.27), .03 * side];
        const pr = .008 * Math.sin(t * 1.3 * sp + (side > 0 ? 0 : 1.5));             // they fidget a little
        paw[0] += pr;
        lines.push([sh, [(sh[0] + paw[0]) / 2 + .01, (sh[1] + paw[1]) / 2 + .02, (sh[2] + paw[2]) / 2 + .015 * side], paw]);
        lines.push(circle(paw[0], paw[1], paw[2], .024, 'sz', 10), circle(paw[0], paw[1] - .008, paw[2], .02, 'sz', 10));
        for (let f = -1; f <= 1; f++) lines.push([[paw[0] - .012, paw[1] + .004, paw[2] + f * .01], [paw[0] - .024, paw[1] + .006, paw[2] + f * .012]]);
        // hind feet: broad webbed flippers raised at the back, paddling in turn
        const kick = .04 * Math.sin(t * 1.1 * sp + (side > 0 ? 0 : Math.PI));
        const root = [.8, .03 + swell(.8), .04 * side], tip = [.93, .13 + kick + swell(.93), .07 * side];
        fin(lines, root, tip, .035, .065, kick * .5, 2);
      }
      // the belly tufts: soft chevrons down the middle
      for (let i = 0; i < 6; i++) {
        const s = .36 + i * .07, y = (q) => pt(s + q, Math.PI / 2)[1] + .006;
        lines.push([[s + .015, y(.015), -.022], [s, y(0), 0], [s + .015, y(.015), .022]]);
      }
      // flat tail, sculling gently
      const sc = (s) => .03 * (s - .84) * 4 * Math.sin(t * 1.4 * sp);
      const tail = [];
      for (let i = 0; i <= 12; i++) {
        const u = i / 12, s = .84 + .24 * u, w = .03 * Math.sin(Math.min(1, u * 1.6 + .2) * Math.PI * .5) * (1 - .3 * u);
        tail.push([[s, .03 + .05 * u + swell(s) + sc(s), w], [s, .03 + .05 * u + swell(s) + sc(s), -w]]);
      }
      lines.push(tail.map((p) => p[0]), tail.map((p) => p[1]));
      for (let i = 2; i <= 12; i += 3) lines.push(tail[i]);
      lines.push([tail[12][0], tail[12][1]]);
      return { lines, tilt: .3, scale: .75 };
    };
  }

  return MODELS;
};
