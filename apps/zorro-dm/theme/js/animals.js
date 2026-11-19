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

  return MODELS;
};
