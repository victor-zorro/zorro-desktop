"""Where the dial sits and how big it is: the hub, the fan's angles, the rings, the apps' cloud."""
import math
import random

from . import config, state

CORNERS = {'bottom-right': 225, 'bottom-left': 315, 'top-right': 135, 'top-left': 45}


def base_rings(hub, u):
    out, r = [], hub + 12 * u
    for w in state.RING_W:
        out.append((r, r + w * u))
        r += w * u
    return out


def fits(rm, span_deg, size):
    """how many icons of this size fit on an arc"""
    return max(1, int(rm * math.radians(span_deg) / (size * 1.8)))    # air between them


def free_spot(rng, pts, span, r_in, limit, reach, size_at, base):
    """a free place for the next app of a slice, as close to the clock as there is room: never
    nearer than CLOUD_GAP to another; None when 90 tries found none within reach"""
    best = None
    for _t in range(90):
        r = rng.uniform(r_in, min(reach, limit))
        sz = size_at(r)
        m = sz * 0.62
        if r - m < r_in or r + m > limit:
            continue
        a = rng.uniform(0, span)
        if r * math.sin(math.radians(min(a, span - a))) < m:
            continue                # too close to the slice's edge
        x, y = r * math.cos(math.radians(a)), r * math.sin(math.radians(a))
        if any((x - qx) ** 2 + (y - qy) ** 2 < ((sz + qs) / 2 * state.CLOUD_GAP) ** 2
               for _qr, _qa, qs, qx, qy in pts):
            continue
        score = r + rng.random() * base * 0.9    # close to the clock, loosely
        if best is None or score < best[0]:
            best = (score, (r, a, sz, x, y))
    return best


def slice_cloud(seed, n, span, r_in, limit, size_at, base):
    """n places in one slice: ([(radius, angle, size, x, y)], all placed?)"""
    rng = random.Random(seed)
    pts = []
    for _k in range(n):
        best, reach = None, (max(q[0] for q in pts) if pts else r_in) + base * 2.5
        for _try in range(4):               # no room yet: look a bit further out
            best = free_spot(rng, pts, span, r_in, limit, reach, size_at, base) or best
            if best:
                break
            reach += base * 2
        if not best:
            return pts, False
        pts.append(best[1])
    return pts, True


class Rings:
    def dial_scale(self):
        """Zorro app → Desktop → Dialer → Size: the rings' width"""
        return min(1.6, max(0.7, float(self.conf.get('size', 1.0))))

    def icon_scale(self):
        return min(1.6, max(0.7, float(self.conf.get('icon_size', 1.0))))

    def ring_size(self, k):
        """icon size on ring k: the further out, the bigger (an icon cloud around the clock)"""
        return state.RING_ICON[min(k, len(state.RING_ICON) - 1)] * self.icon_scale() * self.iu

    def hub_place(self, ru):
        """(cx, cy, hub radius, first angle, last angle, the part of the radius that does not
        scale) for the rings' unit ru"""
        W, H = self.geo.width, self.geo.height
        u, anchor = self.u, self.conf.get('anchor')
        if anchor in CORNERS:           # its own clock in that corner, the fan into the screen
            hub, m = 96 * ru, 40 * u
            cx = m + hub if 'left' in anchor else W - m - hub
            cy = m + hub if 'top' in anchor else H - m - hub
            return cx, cy, hub, CORNERS[anchor] - 60, CORNERS[anchor] + 60, 0
        if anchor == 'orb':             # the hub is the info circle's clock
            if self.orb is None:
                self.orb = config.orb_conf()    # read once: fan() runs on every draw and mouse move
            d, m, corner = self.orb['size'], self.orb['margin'], self.orb['corner']
            cx = m + d / 2 if 'left' in corner else W - m - d / 2
            cy = m + d / 2 if 'top' in corner else H - m - d / 2
            mid = CORNERS.get(corner, 225)
            return cx, cy, d / 2, mid - 60, mid + 60, d / 2
        return W / 2, H / 2, 86 * ru, -90, 270, 0

    def fan(self):
        """(cx, cy, hub radius, first angle, last angle, rings) in window coordinates.
        orb: the hub is the info circle's clock and the rings fan out from its corner into
        the screen (120 degrees); centre: full circle in the middle of the screen.
        Sizes in the unit u (screen) times the Size setting, made smaller where the rings and
        their names would not fit on the screen."""
        u = self.u
        ru = u * self.dial_scale()          # the rings' unit
        edge = 50 * u                       # room outside the outer ring: slice names, '+ slice'
        for _ in range(4):
            cx, cy, hub, a0, a1, fixed = self.hub_place(ru)
            fit = self.reach(cx, cy, a0, a1) - edge
            outer = base_rings(hub, ru)[-1][1]
            if outer <= fit + 0.5:
                break
            ru *= max(0.2, (fit - fixed) / max(1, outer - fixed))
        self.iu = u * ru / (u * self.dial_scale())
        rings = base_rings(hub, ru)
        if self.mode == 'apps' and not self.filter and self.expanded is None:
            rings = self.cloud_rings(cx, cy, a0, a1, rings, fit)
        return cx, cy, hub, a0, a1, rings

    def cloud_rings(self, cx, cy, a0, a1, rings, fit):
        """more apps than three rings hold: the apps as a cloud, as far out as they need (and
        the screen allows); all a bit smaller only if the screen is too small for them"""
        W, H = self.geo.width, self.geo.height
        room = min(min(max(cx, W - cx), max(cy, H - cy)) - 60 * self.u, fit)
        span, r_in, f = (a1 - a0) / max(1, len(self.groups)), rings[0][0], 1.0
        counts = [len(g) for g in self.groups]
        for _ in range(10):
            lay = self.cloud_layout(counts, span, r_in, f, room)
            if not lay[2] or f < 0.62:
                break
            f *= 0.93
        self.cloud = lay[0]
        return [(r_in, max(min(lay[1], room), rings[-1][1]))]

    def reach(self, cx, cy, a0, a1):
        """how far the fan can reach from (cx, cy) between angles a0 and a1 before it leaves
        the screen"""
        W, H = self.geo.width, self.geo.height
        best = float('inf')
        steps = max(1, int((a1 - a0) / 2))
        for j in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * j / steps)
            dx, dy = math.cos(a), math.sin(a)
            tx = (W - cx) / dx if dx > 1e-9 else cx / -dx if dx < -1e-9 else float('inf')
            ty = (H - cy) / dy if dy > 1e-9 else cy / -dy if dy < -1e-9 else float('inf')
            best = min(best, tx, ty)
        return best

    def float_tick(self):
        """15 times a second while the apps float (just the fan); the whole once a second"""
        self.ticks += 1
        floating = self.mode == 'apps' and not self.filter and self.expanded is None and not self.menu
        if self.ticks % 15 == 0:
            self.area.queue_draw()                  # the clock: once a second, all of it
        elif floating:                              # only the fan's box: far cheaper
            cx, cy, _hub, _a0, _a1, rings = self.fan()
            r = int(rings[-1][1] + 10 * self.u)
            self.area.queue_draw_area(int(cx) - r, int(cy) - r, 2 * r, 2 * r)
        return True

    def cloud_layout(self, counts, span, r_in, f, limit):
        """where each app floats in its slice: per slice [(radius, angle into the slice, size)],
        the outer radius used, and whether some did not fit. Free spots, not rows: each next app
        (less used) takes a random free spot as close to the clock as there is room, and the
        further out, the bigger. Seeded per slice, so the cloud looks the same every time the
        apps are the same."""
        base = state.CLOUD_ICON * self.icon_scale() * self.iu * f
        key = (tuple(counts), round(span, 2), round(r_in, 1), round(base, 2), round(limit, 1))
        if key in self.clouds:
            return self.clouds[key]

        def size_at(r):
            return base * min(state.CLOUD_MAX, 1 + state.CLOUD_GROW * (r - r_in) / (base * 1.3))
        out, need, short = [], r_in, False
        for i, n in enumerate(counts):
            pts, placed = slice_cloud(7919 * (i + 1) + n, n, span, r_in, limit, size_at, base)
            short = short or not placed
            need = max([need] + [p[0] + p[2] * 0.7 for p in pts])
            out.append([(r, a, sz) for r, a, sz, _x, _y in pts])
        if len(self.clouds) > 64:
            self.clouds.clear()
        self.clouds[key] = (out, need, short)
        return self.clouds[key]
