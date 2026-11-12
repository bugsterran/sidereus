"""Overview (arch-brief) v2 renderer: one self-contained brief.html from a gate-checked v2 brief.json.

A containment figure (SVG, width 1200): users/screens band on top, the system container (components in rows of <= 3, one
dashed package group, design principles with file:line at the bottom), external systems with numbered uses on the right;
orthogonal labelled arrows, each owning one lane per gap it crosses. Under it a compact role table (one row per box).
Inline <style> only; no script/src/href/URL. Deterministic (input order only). ⚠No route table, sequence or package table.
"""
import itertools
import posixpath

from sidereus.arch_brief_html import e, _text_w

W, PAD = 1200, 20
BAND_Y, BAND_H = 16, 72
CX, CW = 20, 820                 # system container
IN_L, IN_W = 40, 780             # component area inside it
BOX_W, BOX_H, GX = 240, 58, 30
GRP_HEAD, PKG_H, PKG_GX = 26, 46, 10
GRP_H = GRP_HEAD + PKG_H + 12
TITLE_H = 32
LANE, LANE_TOP, LANE_PAD = 16, 18, 10   # ⚠lane spacing > label height (13px): labels on different lanes never meet
GAP_MIN0, GAP_MIN = 30, 26
PR_LINE = 18
EX_X, EX_W, EX_GAP = 880, 300, 14
GUTTER = (24, 28, 32, 36)        # left gutter lanes for component arrows that skip a row
SCREEN_X, SCREEN_W, SCREEN_GX = 260, 300, 30
COLORS = {"screen": ("#2563eb", "#eff6ff"), "component": ("#059669", "#ecfdf5"), "external": ("#d97706", "#fffbeb")}
NUMS = "①②③"

CSS = """
:root { --bg: #ffffff; --band: #f1f5f9; --line: #94a3b8; --text: #0f172a; --muted: #475569; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
       font-family: "Pretendard", "Apple SD Gothic Neo", "Noto Sans KR", system-ui, sans-serif; }
main { max-width: 1240px; margin: 0 auto; padding: 24px 16px 32px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 18px 0 8px; }
.lead { color: var(--muted); margin: 0 0 12px; font-size: 15px; }
.lead small { font-size: 12px; margin-left: 8px; }
/* ⚠min-width keeps text legible: below it the figure scrolls inside .fig, never the page */
.fig { border: 1px solid var(--line); border-radius: 12px; overflow-x: auto; }
svg { display: block; width: 100%; min-width: 900px; max-height: 60vh; height: auto; }
svg text { font-family: inherit; fill: var(--text); }
.t-title { font-size: 14px; font-weight: 700; }
.t-sys { font-size: 15px; font-weight: 700; fill: var(--muted); }
.t-sub { font-size: 12px; fill: var(--muted); }
.t-ev { font-size: 11px; fill: #94a3b8; }
.t-edge { font-size: 11px; fill: var(--muted); }
.edge { fill: none; stroke: #475569; stroke-width: 1.5; }
.deco { fill: none; stroke: #94a3b8; stroke-width: 1.2; stroke-dasharray: 3 3; }
table.legend { width: 100%; border-collapse: collapse; font-size: 14px; line-height: 1.4; }
.legend td { padding: 6px 8px; border-bottom: 1px solid var(--band); vertical-align: top; }
/* ⚠a name never wraps: a long name widens its cell instead */
.legend td.nm { font-weight: 600; width: 200px; white-space: nowrap; }
.legend .nt { color: var(--muted); }
.legend ul { margin: 2px 0 0; padding: 0; list-style: none; font-size: 13px; color: var(--muted); }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 5px; margin-right: 6px; }
.d-screen { background: #2563eb; } .d-component { background: #059669; } .d-external { background: #d97706; }
"""


def _rows(comps):
    """Component rows: plain ones in rows of <= 3 (input order); a pkgs component gets a full-width row of its own."""
    rows, cur = [], []
    for c in comps:
        if "pkgs" in c:
            if cur:
                rows.append(cur)
                cur = []
            rows.append([c])
        else:
            cur.append(c)
            if len(cur) == 3:
                rows.append(cur)
                cur = []
    return rows + ([cur] if cur else [])


def _wrap(s, px, size):
    """Lines of s within px at font size `size` (measured like arch_brief_html._fit), broken at spaces, else between
    characters. ⚠Never cut with an ellipsis: a description that does not fit belongs in the legend, not in the box."""
    out, cur = [], ""

    def fits(t):
        return _text_w(t) * size / 11.0 <= px
    for w in str(s or "").split(" "):
        t = cur + " " + w if cur else w
        if fits(t):
            cur = t
            continue
        if cur:
            out.append(cur)
            cur = ""
        while len(w) > 1 and not fits(w):
            n = len(w) - 1
            while n > 1 and not fits(w[:n]):
                n -= 1
            out.append(w[:n])
            w = w[n:]
        cur = w
    return out + [cur] if cur or not out else out


def _fit_lines(s, px, size, max_lines):
    """(lines, size): the font shrinks down to 10px before more than max_lines run; the text is never cut."""
    lines = _wrap(s, px, size)
    while len(lines) > max_lines and size > 10:
        size -= 1
        lines = _wrap(s, px, size)
    return lines, size


def _texts(x, y, fit, base, cls, anchor=""):
    """<text> per line from baseline y (line height size + 3); a style only when the font shrank."""
    lines, size = fit
    st = ' style="font-size:%dpx"' % size if size != base else ""
    return "".join('<text x="%d" y="%d" class="%s"%s%s>%s</text>' % (x, y + i * (size + 3), cls, st, anchor, e(t))
                   for i, t in enumerate(lines))


def _mid_y(top, h, fit):
    """Baseline of the first line so the lines sit centred in [top, top + h]."""
    lines, size = fit
    return top + (h - (size + 3) * len(lines) + 3) // 2 + size - 2


def _actor_w(name):
    return int(_text_w(name) * 13 / 11) + 24


def _ext_text(x):
    """(head fit, [use fit]) of an external: name, and «① name» per use (notes go to the legend)."""
    return _fit_lines(x["name"], EX_W - 20, 14, 2), [_fit_lines("%s %s" % (NUMS[i], u["name"]), EX_W - 24, 12, 2)
                                                     for i, u in enumerate(x["uses"])]


def _principle(p):
    """(text lines, evidence shown, evidence full) — evidence as basename:line, the full path in a tooltip."""
    full = "%s:%d" % (p["evidence"]["file"], p["evidence"]["line"])
    short = "%s:%d" % (posixpath.basename(p["evidence"]["file"]) or p["evidence"]["file"], p["evidence"]["line"])
    return _wrap("· " + p["text"], IN_W - _text_w(short) - 20, 12), short, full


def _plan(b, rows):
    """Component<->component arrows only (screens and externals are bundled in _links): per arrow either a straight
    vertical ("v": adjacent rows sharing a column) or lanes in the gaps it uses (gap g = above row g; the left gutter
    for a skipped row). Returns (plan, lane arrows per gap, straight arrows per gap)."""
    level, col = {}, {}
    for r, row in enumerate(rows):
        for c, x in enumerate(row):
            level[x["id"]], col[x["id"]] = r, (None if "pkgs" in x else c)
    gaps, vg, plan, gut = [[] for _ in range(len(rows) + 1)], [[] for _ in range(len(rows) + 1)], {}, []
    for k, a in enumerate(b["arrows"]):
        f, t = a["from"], a["to"]
        if f not in level or t not in level or f == t:
            continue
        s, d = level[f], level[t]
        if abs(d - s) == 1 and (col[f] == col[t] or None in (col[f], col[t])):
            plan[k] = {"kind": "v", "g": max(s, d), "down": d > s}
            vg[max(s, d)].append(k)
            continue
        if d > s:
            p = {"sa": "bot", "sb": "top", "use": [s + 1] if d == s + 1 else [s + 1, d]}
        elif d == s:
            p = {"sa": "bot", "sb": "bot", "use": [s + 1]}
        else:
            p = {"sa": "top", "sb": "bot", "use": [s] if d == s - 1 else [s, d + 1]}
        p["kind"] = "lane"
        if len(p["use"]) == 2:
            gut.append(k)
        for g in p["use"]:
            gaps[g].append(k)
        plan[k] = p
    # ⚠Longer gutter spans take the outer x: a run into the gutter never crosses a vertical it is nested in.
    for i, k in enumerate(sorted(gut, key=lambda k: (-abs(plan[k]["use"][1] - plan[k]["use"][0]), k))):
        plan[k]["gx"] = GUTTER[i % len(GUTTER)]
    return plan, gaps, vg


def _screen_links(b):
    """[(screen, label fit or None, down, up)] — one arrow per screen to the system, labelled with its arrows' labels."""
    out = []
    for x in b["screens"]:
        scr = set(y["id"] for y in b["screens"])
        # a screen->screen arrow is not a link to the system: the legend still lists it
        mine = [a for a in b["arrows"] if x["id"] in (a["from"], a["to"]) and not (a["from"] in scr and a["to"] in scr)]
        labels = []
        for a in mine:
            if a["label"] not in labels:
                labels.append(a["label"])
        fit = _fit_lines(" · ".join(labels), 300, 11, 2) if labels else None
        out.append((x, fit, any(a["from"] == x["id"] for a in mine), any(a["to"] == x["id"] for a in mine)))
    return out


def _geom(b):
    """Positions of everything (integers): boxes {id: (x, y, w, h)}, rows, gap tops/heights, plan, externals rows."""
    rows = _rows(b["system"]["components"])
    plan, gaps, vg = _plan(b, rows)
    pos = {}
    sx = max(SCREEN_X, 40 + max(_actor_w(a["name"]) for a in b["actors"]) + 60)
    n = len(b["screens"])
    sw = min(SCREEN_W, (W - PAD - 20 - sx - (n - 1) * SCREEN_GX) // n)
    for i, x in enumerate(b["screens"]):
        pos[x["id"]] = (sx + i * (sw + SCREEN_GX), BAND_Y + 10, sw, BAND_H - 20)
    lines = max([len(f[0]) for _x, f, _d, _u in _screen_links(b) if f] or [1])
    h0 = max(GAP_MIN0, 13 * lines + 14)
    tops, hs = [BAND_Y + BAND_H], [h0]
    cy = BAND_Y + BAND_H + h0
    y = cy + TITLE_H
    for r, row in enumerate(rows):
        rh = GRP_H if "pkgs" in row[0] else BOX_H
        for c, x in enumerate(row):
            pos[x["id"]] = (IN_L, y, IN_W, rh) if "pkgs" in x else (IN_L + c * (BOX_W + GX), y, BOX_W, rh)
        y += rh
        n = len(gaps[r + 1])
        # a gap with straight arrows keeps a free band under its lanes for their side labels
        h = (LANE * n + LANE_PAD if n else 0) + (16 if vg[r + 1] else 0)
        h = max(GAP_MIN if r + 1 < len(rows) else 12, h)
        tops.append(y)
        hs.append(h)
        y += h
    pr_top = y
    y += PR_LINE * sum(len(_principle(p)[0]) for p in b["system"]["principles"]) + 12
    ey, erows = cy, {}
    for x in b["externals"]:
        head, uses = _ext_text(x)
        hh = 12 + (head[1] + 3) * len(head[0])
        rhs = [6 + (u[1] + 3) * len(u[0]) for u in uses]
        h = hh + sum(rhs) + 6
        pos[x["id"]] = (EX_X, ey, EX_W, h)
        erows[x["id"]] = [ey + hh + sum(rhs[:i]) + rhs[i] // 2 for i in range(len(rhs))]
        ey += h + EX_GAP
    bottom = max(y, ey - EX_GAP + 10)    # the container reaches past every external's middle (its link starts there)
    return {"pos": pos, "rows": rows, "tops": tops, "hs": hs, "gaps": gaps, "vg": vg, "plan": plan,
            "cont": (CX, cy, CW, bottom - cy), "pr_top": pr_top, "erows": erows, "H": bottom + PAD}


def _stubs(p, g, att, k):
    """(run lo, run hi, [(x, +1 joins below / -1 joins above)]) of a lane arrow's horizontal run in gap g."""
    da = -1 if p["sa"] == "bot" else 1       # the source sits above the gap when its bottom side is used
    db = -1 if p["sb"] == "bot" else 1
    xa, xb = att[(k, "xa")], att[(k, "xb")]
    if len(p["use"]) == 1:
        xf, xt, st = xa, xb, [(xa, da), (xb, db)]
    elif g == p["use"][0]:
        dn = 1 if p["use"][1] > p["use"][0] else -1
        xf, xt, st = xa, p["gx"], [(xa, da), (p["gx"], dn)]
    else:
        dn = 1 if p["use"][1] > p["use"][0] else -1
        xf, xt, st = p["gx"], xb, [(p["gx"], -dn), (xb, db)]
    return min(xf, xt), max(xf, xt), st


def _order(ks, info, memo):
    """Lane order with the fewest stub-over-run crossings (exhaustive <= 6 lanes, else greedy). ⚠Memoised: re-asked often."""
    key = tuple((k, info[k][0], info[k][1], tuple(info[k][2])) for k in ks)
    if key in memo:
        return memo[key]
    c = dict(((a, b), sum(1 for x, d in info[a][2] if d > 0 and info[b][0] < x < info[b][1]) +
              sum(1 for x, d in info[b][2] if d < 0 and info[a][0] < x < info[a][1])) for a in ks for b in ks if a != b)

    def total(o):        # c[(a, b)]: a above b — a's stubs going down cross b's run, b's stubs going up cross a's run
        return sum(c[(o[i], o[j])] for i in range(len(o)) for j in range(i + 1, len(o)))
    if len(ks) <= 6:
        order = list(min(itertools.permutations(ks), key=lambda o: (total(o), o)))
    else:
        order = []
        for k in ks:
            best = min(range(len(order) + 1), key=lambda i: (total(order[:i] + [k] + order[i:]), i))
            order.insert(best, k)
        moved = True
        while moved:         # move one lane to its best slot while that lowers the total
            moved = False
            for k in list(order):
                rest = [x for x in order if x != k]
                cand = min((rest[:i] + [k] + rest[i:] for i in range(len(rest) + 1)), key=lambda o: (total(o), o))
                if total(cand) < total(order):
                    order, moved = cand, True
            for i in range(len(order) - 4):   # then any 5 neighbouring lanes in their best order
                cand = min((order[:i] + list(w) + order[i + 5:] for w in itertools.permutations(order[i:i + 5])),
                           key=lambda o: (total(o), o))
                if total(cand) < total(order):
                    order, moved = cand, True
    memo[key] = order
    return order


def routes(b):
    """({arrow index: (points, label x, label y, label w)}, geometry) for component<->component arrows — pure.
    Attach orders start from a nesting heuristic, then each side's order is searched for the fewest crossings."""
    G = _geom(b)
    pos, plan = G["pos"], G["plan"]
    sides = {}
    for k in sorted(plan):
        p, a = plan[k], b["arrows"][k]
        if p["kind"] != "lane":
            continue
        fx, tx = pos[a["from"]], pos[a["to"]]
        sides.setdefault((a["from"], p["sa"]), []).append((p.get("gx", tx[0] + tx[2] // 2), k, "xa"))
        sides.setdefault((a["to"], p["sb"]), []).append((p.get("gx", fx[0] + fx[2] // 2), k, "xb"))
    for (bid, _s), lst in sides.items():
        x, _y, w, _h = pos[bid]
        # left-going lines first, then right-going; within each the farther target sits outer, so runs nest
        lst.sort(key=lambda t: (t[0] >= x + w // 2, -t[0], t[1]))
    memo = {}
    raw = _raw(b, G, _attach(pos, sides), memo)
    best = _crossings(raw)
    for _pass in range(2):
        for key in sorted(sides):
            if best == 0 or not 1 < len(sides[key]) <= 5:
                continue
            keep = sides[key]
            for perm in itertools.permutations(keep):
                sides[key] = list(perm)
                cand = _raw(b, G, _attach(pos, sides), memo)
                n = _crossings(cand)
                if n < best:
                    best, raw, keep = n, cand, list(perm)
            sides[key] = keep
    return _labels(b, raw, G), G


def _attach(pos, sides):
    """{(k, "xa"|"xb"): x} — spread evenly in side order; the wide package group takes x right above/below the other end."""
    att = {}
    for (bid, _s), lst in sorted(sides.items()):
        x, _y, w, _h = pos[bid]
        if w <= 2 * BOX_W:
            for i, (_o, k, end) in enumerate(lst):
                att[(k, end)] = x + (i + 1) * w // (len(lst) + 1)
            continue
        prev = None          # a run into the gutter then stays short, clear of straight arrows dropping into the group
        for o, k, end in lst:
            px = min(max(o, x + 12), x + w - 12)
            px = px if prev is None or px >= prev + 14 else prev + 14
            att[(k, end)] = prev = px
    return att


def _crossings(raw):
    """Count of interior horizontal/vertical crossings between different arrows."""
    hs, vs = [], []
    for k, (pts, _r, _l) in raw.items():
        for q, r in zip(pts, pts[1:]):
            if q[1] == r[1] and q[0] != r[0]:
                hs.append((k, min(q[0], r[0]), max(q[0], r[0]), q[1]))
            elif q[0] == r[0] and q[1] != r[1]:
                vs.append((k, q[0], min(q[1], r[1]), max(q[1], r[1])))
    return sum(1 for k1, x0, x1, y in hs for k2, x, y0, y1 in vs if k1 != k2 and x0 < x < x1 and y0 < y < y1)


def _raw(b, G, att, memo):
    """{k: (points, lane run or None, first lane y or gap index)} for one choice of attach points."""
    pos, plan = G["pos"], G["plan"]
    lane = {}
    for g, ks in enumerate(G["gaps"]):
        info = dict((k, _stubs(plan[k], g, att, k)) for k in ks)
        for i, k in enumerate(_order(ks, info, memo)):
            lane[(g, k)] = G["tops"][g] + LANE_TOP + LANE * i
    raw = {}
    for k in sorted(plan):
        p, a = plan[k], b["arrows"][k]
        if p["kind"] == "lane":
            l1, xa, xb = lane[(p["use"][0], k)], att[(k, "xa")], att[(k, "xb")]
            pts = [(xa, _side_y(pos[a["from"]], p["sa"])), (xa, l1)]
            if len(p["use"]) == 2:
                l2 = lane[(p["use"][1], k)]
                pts += [(p["gx"], l1), (p["gx"], l2), (xb, l2)]
            else:
                pts.append((xb, l1))
            pts.append((xb, _side_y(pos[a["to"]], p["sb"])))
            raw[k] = (_clean(pts), (xa, pts[2][0]), l1)
    for g, ks in enumerate(G["vg"]):
        top, bot = G["tops"][g], G["tops"][g] + G["hs"][g]
        runs = [(min(q[0], r[0]), max(q[0], r[0])) for pts, _r, _l in raw.values() for q, r in zip(pts, pts[1:])
                if q[1] == r[1] and top <= q[1] <= bot]
        taken = [q[0] for pts, _r, _l in raw.values() for q, r in zip(pts, pts[1:])
                 if q[0] == r[0] and min(q[1], r[1]) < bot and max(q[1], r[1]) > top]
        for k in ks:
            a = b["arrows"][k]
            f, t = pos[a["from"]], pos[a["to"]]
            lo, hi = max(f[0], t[0]) + 12, min(f[0] + f[2], t[0] + t[2]) - 12
            mid = (lo + hi) // 2
            x = min(range(lo, hi + 1, 2), key=lambda c: (sum(1 for r0, r1 in runs if r0 < c < r1),
                                                          any(abs(c - u) < 8 for u in taken), abs(c - mid), c))
            taken.append(x)
            down = plan[k]["down"]
            raw[k] = ([(x, f[1] + f[3] if down else f[1]), (x, t[1] if down else t[1] + t[3])], None, g)
    return raw


def _side_y(r, side):
    return r[1] + r[3] if side == "bot" else r[1]


def _clean(pts):
    out = [pts[0]]
    for q in pts[1:]:
        if q != out[-1]:
            out.append(q)
    return out


def _hit(p, q):
    return p[0] < q[0] + q[2] and q[0] < p[0] + p[2] and p[1] < q[1] + q[3] and q[1] < p[1] + p[3]


def _labels(b, raw, G):
    """{k: (points, label x, label y, label w)}: a lane label slides along its own run, a straight arrow's label sits
    beside its line; each spot minimises lines under it and never sits on another label."""
    segs = [(k, q, r) for k, (pts, _r, _l) in raw.items() for q, r in zip(pts, pts[1:])]
    cx0, cy0, cw, ch = G["cont"]
    placed, out = [], {}

    def score(k, rect):
        n = 1000 * sum(_hit(rect, p) for p in placed)
        n += 1000 * (rect[0] < cx0 + 2 or rect[0] + rect[2] > cx0 + cw - 2)
        for kk, q, r in segs:
            wt = 3 if kk == k else 10      # its own stubs count too: a label should not sit on its own corner
            if q[0] == r[0] and rect[0] - 2 < q[0] < rect[0] + rect[2] + 2 and min(q[1], r[1]) < rect[1] + rect[3] \
                    and max(q[1], r[1]) > rect[1]:
                n += wt
            elif kk != k and q[1] == r[1] and rect[1] - 2 < q[1] < rect[1] + rect[3] + 2 and min(q[0], r[0]) < rect[0] + rect[2] \
                    and max(q[0], r[0]) > rect[0]:
                n += 10
        return n
    for k in sorted(raw, key=lambda k: (raw[k][1] is None, k)):
        pts, run, l1 = raw[k]
        lw = _text_w(b["arrows"][k]["label"])
        cands = []
        if run is not None:          # lane: slide along the run, label above its lane
            a, z = min(run), max(run)
            mid, reach = (a + z) // 2, (z - a) // 2 + lw // 2 + 8   # may hang past a short run to clear its corners
            for off in [0] + [s * d for s in range(6, reach + 1, 6) for d in (1, -1)]:
                cands.append((mid + off - lw // 2, l1 - 15, lw, 13))
        else:                        # straight: beside the vertical, anywhere along the gap
            x, g = pts[0][0], l1
            for top in range(G["tops"][g] + 2, G["tops"][g] + G["hs"][g] - 14, 2):
                cands += [(x + 6, top, lw, 13), (x - 6 - lw, top, lw, 13)]
        best = min(cands, key=lambda rc: score(k, rc))
        placed.append(best)
        out[k] = (pts, best[0] + lw // 2, best[1] + 11, lw)
    return out


def _links(b, G):
    """Bundled links: per screen one vertical to the container top (labels joined), per external one short horizontal
    from the container's right edge at the external's middle; markers follow the directions of the brief arrows."""
    pos, (cx, cy, cw, _ch) = G["pos"], G["cont"]
    out = []
    for x, fit, down, up in _screen_links(b):
        sx, sy, sw, sh = pos[x["id"]]
        lo, hi = max(sx + 10, cx + 20), min(sx + sw - 10, cx + cw - 20)
        if lo <= hi:
            xm = max(lo, min(hi, sx + sw // 2))
            pts = [(xm, sy + sh), (xm, cy)]
        else:                        # a screen right of the container: down, then over to its edge
            mid = (sy + sh + cy) // 2
            pts = [(sx + sw // 2, sy + sh), (sx + sw // 2, mid), (cx + cw - 20, mid), (cx + cw - 20, cy)]
        out.append(("screen", x["id"], pts, down, up, fit))
    for x in b["externals"]:
        ex, ey, _ew, eh = pos[x["id"]]
        mine = [a for a in b["arrows"] if x["id"] in (a["from"], a["to"])]
        ym = ey + eh // 2
        out.append(("external", x["id"], [(cx + cw, ym), (ex, ym)], any(a["to"] == x["id"] for a in mine),
                    any(a["from"] == x["id"] for a in mine), None))
    return out


def figure(b):
    rt, G = routes(b)
    pos = G["pos"]
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, G["H"], e(b["title"])),
           '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#475569"/></marker></defs>',
           '<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="#f1f5f9" stroke="#94a3b8"/>' % (PAD, BAND_Y, W - 2 * PAD, BAND_H)]
    na = len(b["actors"])
    for i, a in enumerate(b["actors"]):
        ay = BAND_Y + (BAND_H // 2 - 12 if na == 1 else 8 + i * 30)
        name, pw = a["name"], _actor_w(a["name"])
        out.append('<g data-actor="%s"><rect x="40" y="%d" width="%d" height="24" rx="12" fill="#ffffff" stroke="#64748b"/>'
                   '<text x="%d" y="%d" class="t-sub" text-anchor="middle">%s</text></g>' % (e(a["id"]), ay, pw, 40 + pw // 2, ay + 16, e(name)))
        sx, sy, _sw, sh = pos[b["screens"][min(i, len(b["screens"]) - 1)]["id"]]
        mx = (40 + pw + sx) // 2
        out.append('<path class="deco" d="M%d,%d L%d,%d L%d,%d L%d,%d"/>' % (40 + pw, ay + 12, mx, ay + 12, mx, sy + sh // 2, sx, sy + sh // 2))
    for x in b["screens"]:
        out.append(_box(x, pos[x["id"]], "screen", x["modules"]))
    cx, cy, cw, ch = G["cont"]
    out.append('<g data-system="1"><rect x="%d" y="%d" width="%d" height="%d" rx="14" fill="#f8fafc" stroke="#64748b" stroke-width="1.4"/>'
               '<text x="%d" y="%d" class="t-sys">%s</text></g>' % (cx, cy, cw, ch, cx + 16, cy + 22, e(b["system"]["name"])))
    for c in b["system"]["components"]:
        out.append(_group(c, pos[c["id"]]) if "pkgs" in c else _box(c, pos[c["id"]], "component", c["modules"]))
    y = G["pr_top"]
    out.append('<path class="deco" d="M%d,%d L%d,%d"/>' % (IN_L, y + 2, IN_L + IN_W, y + 2))
    ln = 0
    for i, p in enumerate(b["system"]["principles"]):
        lines, short, full = _principle(p)
        for j, t in enumerate(lines):
            ev = '<tspan class="t-ev" dx="10"><title>%s</title>%s</tspan>' % (e(full), e(short)) if j == 0 else ""
            out.append('<text x="%d" y="%d" class="t-sub" data-principle="%d">%s%s</text>'
                       % (IN_L + (10 if j else 0), y + 16 + PR_LINE * ln, i + 1, e(t), ev))
            ln += 1
    for x in b["externals"]:
        out.append(_ext(x, pos[x["id"]], G["erows"][x["id"]]))
    for kind, bid, pts, fwd, back, fit in _links(b, G):
        mk = (' marker-end="url(#arr)"' if fwd else "") + (' marker-start="url(#arr)"' if back else "")
        g = '<g data-link="%s %s"><path d="%s" class="edge"%s/>' % (kind, e(bid), _d(pts), mk)
        if fit:
            top = G["tops"][0] + (G["hs"][0] - 13 * len(fit[0])) // 2 + 10
            g += _texts(pts[0][0] + 6, top, fit, 11, "t-edge")
        out.append(g + "</g>")
    for k, a in enumerate(b["arrows"]):
        if k not in rt:
            continue
        pts, lx, ly, _lw = rt[k]
        out.append('<g data-arrow="%s %s" data-edges="%s"><path d="%s" class="edge" marker-end="url(#arr)"/>'
                   '<text x="%d" y="%d" class="t-edge" text-anchor="middle">%s</text></g>' % (
                       e(a["from"]), e(a["to"]), e(" ".join(str(i) for i in a["edges"])), _d(pts), lx, ly, e(a["label"])))
    out.append("</svg>")
    return "\n".join(out)


def _d(pts):
    return "M%d,%d " % pts[0] + " ".join("L%d,%d" % q for q in pts[1:])


def _box(x, r, kind, mods):
    bx, by, bw, bh = r
    stroke, fill = COLORS[kind]
    ids = " ".join(mods)
    fit = _fit_lines(x["name"], bw - 20, 14, 3)
    return ('<g data-box="%s" data-kind="%s" data-mods="%s"><title>%s</title>'
            '<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="%s" stroke="%s" stroke-width="1.4"/>'
            '%s</g>' % (e(x["id"]), kind, e(ids), e(x["name"] + " — " + ids), bx, by, bw, bh, fill, stroke,
                        _texts(bx + 10, _mid_y(by, bh, fit), fit, 14, "t-title")))


def _group(c, r):
    gx, gy, gw, gh = r
    stroke, fill = COLORS["component"]
    ids = " ".join(i for p in c["pkgs"] for i in p["modules"])
    out = ['<g data-box="%s" data-kind="component" data-mods="%s"><title>%s</title>'
           '<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="#ffffff" stroke="%s" stroke-width="1.4" stroke-dasharray="6 4"/>'
           '%s' % (e(c["id"]), e(ids), e(c["name"] + " — " + ids), gx, gy, gw, gh, stroke,
                   _texts(gx + 10, gy + 18, _fit_lines(c["name"], gw - 20, 14, 1), 14, "t-title"))]
    n = len(c["pkgs"])
    pw = (gw - 20 - (n - 1) * PKG_GX) // n
    for i, p in enumerate(c["pkgs"]):
        px = gx + 10 + i * (pw + PKG_GX)
        fit = _fit_lines(p["name"], pw - 16, 14, 2)
        out.append('<g data-pkg="%d"><rect x="%d" y="%d" width="%d" height="%d" rx="8" fill="%s" stroke="%s"/>%s</g>' % (
            i + 1, px, gy + GRP_HEAD, pw, PKG_H, fill, stroke, _texts(px + 8, _mid_y(gy + GRP_HEAD, PKG_H, fit), fit, 14, "t-title")))
    return "\n".join(out) + "</g>"


def _ext(x, r, rows):
    ex, ey, ew, eh = r
    stroke, fill = COLORS["external"]
    ids = " ".join(x["modules"])
    head, uses = _ext_text(x)
    out = ['<g data-box="%s" data-kind="external" data-mods="%s"><title>%s</title>'
           '<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="%s" stroke="%s" stroke-width="1.4"/>'
           '%s' % (e(x["id"]), e(ids), e(x["name"] + " — " + ids), ex, ey, ew, eh, fill, stroke,
                   _texts(ex + 10, ey + 20, head, 14, "t-title"))]
    for i, fit in enumerate(uses):
        top = rows[i] - ((fit[1] + 3) * len(fit[0]) - 3) // 2 + fit[1] - 2
        out.append('<g data-use="%d">%s</g>' % (i + 1, _texts(ex + 12, top, fit, 12, "t-sub")))
    return "\n".join(out) + "</g>"


def _uses(b, x):
    """[(«① name», note, «← users»)] then one «← names» line for its arrows without a use: the per-arrow detail the
    figure bundles into one link."""
    names = dict((y["id"], y["name"]) for y in b["screens"] + b["system"]["components"] + b["externals"])

    def users(arrows):
        out = []
        for a in arrows:
            n = names.get(a["to"] if a["from"] == x["id"] else a["from"], "")
            if n not in out:
                out.append(n)
        return ("← " + ", ".join(out)) if out else ""
    mine = [a for a in b["arrows"] if x["id"] in (a["from"], a["to"])]
    items = []
    for i, u in enumerate(x["uses"]):
        who = users([a for a in mine if a.get("use") == i + 1 and a["to"] == x["id"]])
        items.append(("%s %s" % (NUMS[i], u["name"]), u.get("note"), who))
    rest = users([a for a in mine if not (a.get("use") and a["to"] == x["id"])])
    return items + ([(rest, None, None)] if rest else [])


def legend(b):
    """Role table in figure order, one row per box: name | role · note, then packages or numbered uses as one-line items
    (number, name and note in one element so they cannot drift apart)."""
    rows = [(x, "screen", []) for x in b["screens"]]
    rows += [(x, "component", [(p["name"], p.get("note"), None) for p in x.get("pkgs", [])]) for x in b["system"]["components"]]
    rows += [(x, "external", _uses(b, x)) for x in b["externals"]]
    out = ['<table class="legend"><tbody>']
    for x, kind, items in rows:
        note = '<span class="nt"> · %s</span>' % e(x["note"]) if x.get("note") else ""
        lst = "<ul>%s</ul>" % "".join("<li>%s%s%s</li>" % (e(n), " — " + e(t) if t else "", " · " + e(w) if w else "")
                                       for n, t, w in items) if items else ""
        out.append('<tr data-box="%s"><td class="nm"><span class="dot d-%s"></span>%s</td><td>%s%s%s</td></tr>'
                   % (e(x["id"]), kind, e(x["name"]), e(x["role"]), note, lst))
    out.append("</tbody></table>")
    return "\n".join(out)


def render(b, by="", fig=None):
    """brief.html of a gate-checked v2 brief; fig = a hand-layout svg (arch_brief_layout), by = drawing session id."""
    heads = b.get("heads") or {}
    return "\n".join([
        "<!doctype html>", '<html><head><meta charset="utf-8">',
        "<title>%s</title>" % e(b["title"]), "<style>%s</style>" % CSS, "</head><body><main>",
        "<h1>%s</h1>" % e(b["title"]),
        '<p class="lead">%s<small>commit %s%s</small></p>' % (e(b["what"]), e(str(b.get("commit") or "")[:7]), " · drawn by " + e(by) if by else ""),
        '<section class="arch"><h2>%s</h2><div class="fig">' % e(heads.get("arch") or "Architecture"), figure(b) if fig is None else fig, "</div></section>",
        '<section class="roles"><h2>%s</h2>' % e(heads.get("legend") or "Components"), legend(b), "</section>",
        "</main></body></html>", ""])
