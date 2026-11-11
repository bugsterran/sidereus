"""Overview (arch-brief) renderer: one self-contained brief.html from a gate-checked brief.json.

Two sections only — an SVG architecture figure (boxes in bands, orthogonal arrows) and the decision-order table.
Inline <style> only; no script, link, src, href or URL, so the file opens offline and leaks nothing.
Deterministic: the same brief gives the same bytes (no clock, no dict-order dependence beyond the input lists).
Stdlib only; imports nothing from sidereus.
"""
import html

W = 1200                  # SVG view width
PAD = 24                  # outer padding inside the figure
BAND_HEAD = 30            # band label strip above its boxes
BOX_H = 84
GAP_X, GAP_Y = 28, 34     # gaps between boxes; GAP_Y also leaves room for arrow labels between rows
BAND_GAP = 26
ROW_MAX = 5               # 6+ boxes in a band wrap to a second row
BOX_W_MAX = 260
# Light fills per band (top to bottom), stroke + fill.
PALETTE = (("#2563eb", "#eff6ff"), ("#059669", "#ecfdf5"), ("#d97706", "#fffbeb"), ("#7c3aed", "#f5f3ff"))

CSS = """
:root { --bg: #ffffff; --band: #f1f5f9; --line: #94a3b8; --text: #0f172a; --muted: #475569; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
       font-family: "Pretendard", "Apple SD Gothic Neo", "Noto Sans KR", system-ui, sans-serif; }
main { max-width: 1240px; margin: 0 auto; padding: 32px 16px 48px; }
h1 { font-size: 24px; margin: 0 0 6px; }
h2 { font-size: 19px; margin: 36px 0 12px; }
.lead { color: var(--muted); margin: 0 0 20px; font-size: 14px; }
.fig { border: 1px solid var(--line); border-radius: 12px; overflow-x: auto; }
/* min-width keeps box text legible on phones (scrolls inside .fig); it must stay below
   the .fig inner width at a 900px viewport (900 - 2*16 padding - 2 border = 866) */
svg { display: block; width: 100%; min-width: 840px; height: auto; }
svg text { font-family: inherit; fill: var(--text); }
.t-band { font-size: 13px; font-weight: 700; fill: var(--muted); letter-spacing: .5px; }
.t-title { font-size: 14px; font-weight: 700; }
.t-sub { font-size: 12px; fill: var(--muted); }
.t-ids { font-size: 10px; fill: #94a3b8; }
.t-edge { font-size: 11px; fill: var(--muted); }
.edge { fill: none; stroke: #475569; stroke-width: 1.6; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; }
td.n { color: var(--muted); width: 40px; }
/* a long file:line token must wrap at narrow widths, not widen the table past main */
td.ev { font-family: ui-monospace, Menlo, monospace; font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
.by { color: var(--muted); font-size: 13px; margin: 0 0 8px; }
"""


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def _cut(s, n):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"


def _wrap2(s, px, size):
    """At most two lines within px at font size `size` (measured, not counted: Hangul is ~1em); the second is cut with an ellipsis."""
    s = str(s or "")
    if _fit(s, px, size) == s:
        return [s]
    n = max(1, len(_fit(s, px, size)) - 1)   # chars that fit on line one (drop the ellipsis)
    cut = s.rfind(" ", 0, n + 1)
    cut = cut if cut > n // 2 else n
    return [s[:cut].rstrip(), _fit(s[cut:].lstrip(), px, size)]


LANE = 16                 # ⚠lane spacing >= label height (13px), so a label above its lane never meets the next lane's
LANE_TOP = 18             # first lane sits this far below the gap's top edge (its label fits above it)
LANE_PAD = 10             # gap height for n lanes = LANE * n + LANE_PAD


def _grid(brief):
    """[(band, [[(box id, x, w)] per row])] — x only; row y depends on how many arrow lanes each gap needs."""
    out = []
    for b in brief["bands"]:
        mine = [x for x in brief["boxes"] if x["band"] == b["id"]]
        n = len(mine)
        cols = max(1, n if n <= ROW_MAX else (n + 1) // 2)
        bw = min(BOX_W_MAX, (W - 2 * PAD - 32 - (cols - 1) * GAP_X) // cols)
        rows = []
        for k, x in enumerate(mine):
            r, c = divmod(k, cols)
            in_row = min(cols, n - r * cols)
            left = (W - (in_row * bw + (in_row - 1) * GAP_X)) // 2
            if c == 0:
                rows.append([])
            rows[-1].append((x["id"], left + c * (bw + GAP_X), bw))
        out.append((b, rows))
    return out


def _text_w(s):
    """Estimated .t-edge (11px) width: wide (CJK/Hangul) glyphs ~11px, others ~6.5px."""
    return int(sum(11 if ord(c) >= 0x1100 else 6.5 for c in str(s or ""))) + 6


def _fit(s, px, size):
    """s cut with an ellipsis so its estimated width at font size `size` stays within px (a char count overflows on Hangul)."""
    s = "" if s is None else str(s)
    if _text_w(s) * size / 11.0 <= px:
        return s
    while s and _text_w(s + "…") * size / 11.0 > px:
        s = s[:-1]
    return s + "…"


def _title_w(s):
    """Estimated .t-band (13px bold, .5px spacing) width, on the wide side so lines keep clear of it."""
    s = str(s or "")
    return sum(14 if ord(c) >= 0x1100 else 9 for c in s) + len(s) // 2 + 6


def _plan(brief, grid):
    """Per drawn arrow: rows, sides, attach x, vertical lane x; plus the arrows using each gap (gap g = above row g)."""
    where, rowlist, rows3 = {}, [], []
    for b, rows in grid:
        for r, row in enumerate(rows):
            # ⚠A first row's top attach points and any vertical through the band cross its title strip: keep x past it.
            block = (PAD + 16 - 4, PAD + 16 + _title_w(b["name"]) + 4) if r == 0 else None
            for bid, x, w in row:
                where[bid] = (len(rowlist), x, w, block)
            rowlist.append(row)
            rows3.append((0, 0, [(x, 0, w, 0) for _bid, x, w in row], block))
    gaps = [[] for _ in range(len(rowlist) + 1)]
    plan, used_xv, search = {}, [], {}
    for k, a in enumerate(brief.get("arrows") or []):
        if a["from"] not in where or a["to"] not in where or a["from"] == a["to"]:
            continue
        (ri, ax, aw, _ba), (rj, bx, bw, _bb) = where[a["from"]], where[a["to"]]
        ca, cb = ax + aw // 2, bx + bw // 2
        xv = None
        if ri == rj:   # same row: always around the row (a side-to-side line put its label over both boxes)
            up = len(gaps[ri]) <= len(gaps[ri + 1])
            sa = sb = "top" if up else "bot"
            use = [ri if up else ri + 1]
        else:
            if rj > ri:
                sa, sb, g1, g2, mid = "bot", "top", ri + 1, rj, rows3[ri + 1:rj]
            else:
                sa, sb, g1, g2, mid = "top", "bot", ri, rj + 1, rows3[rj + 1:ri]
            use = [g1] if g1 == g2 else [g1, g2]
            if mid:
                lo, hi = min(ri, rj), max(ri, rj)
                base = _lane_x(ca, cb, mid)
                # Arrows crossing the same rows get their own vertical (bases from different candidates may differ by 1px).
                xv = _free_x(base, mid, [u for u, ul, uh in used_xv if ul < hi and lo < uh])
                used_xv.append((xv, lo, hi))
                search[k] = (base, mid, lo, hi)
        for g in use:
            gaps[g].append(k)
        plan[k] = {"ri": ri, "rj": rj, "sa": sa, "sb": sb, "gaps": use, "xv": xv,
                   "other_a": cb if xv is None else xv, "other_b": ca if xv is None else xv}
    # Attach points spread along each used side, ordered by where the line heads (fewer crossings, no shared ends).
    sides = {}
    for k, p in plan.items():
        a = brief["arrows"][k]
        sides.setdefault((a["from"], p["sa"]), []).append((p["other_a"], k, 0))
        sides.setdefault((a["to"], p["sb"]), []).append((p["other_b"], k, 1))
    for (bid, side), lst in sides.items():
        _r, x, w, block = where[bid]
        lo = x
        if side == "top" and block and block[0] < x + w and x < block[1] and x + w - block[1] >= 40:
            lo = max(x, block[1])
        lst.sort()
        for i, (_o, k, end) in enumerate(lst):
            plan[k]["xb" if end else "xa"] = lo + (i + 1) * (x + w - lo) // (len(lst) + 1)
    # ⚠Attach stubs are only known now: a vertical lane on another arrow's stub x in a gap it crosses shares a line with it.
    stubs = [(k, p["xa"], p["ri"] + (p["sa"] == "bot")) for k, p in plan.items()] + \
        [(k, p["xb"], p["rj"] + (p["sb"] == "bot")) for k, p in plan.items()]
    for k in sorted(search):
        base, mid, lo, hi = search[k]
        taken = [x for kk, x, g in stubs if kk != k and lo < g <= hi] + \
            [plan[kk]["xv"] for kk, (_b, _m, l2, h2) in search.items() if kk != k and l2 < hi and lo < h2]
        if any(abs(plan[k]["xv"] - t) < _NEAR for t in taken):
            plan[k]["xv"] = _free_x(base, mid, taken, plan[k]["xv"])
    for g, ks in enumerate(gaps):
        gaps[g] = _order(g, ks, plan, brief)
    return plan, gaps


_NEAR = 6                 # verticals closer than this read as one line


def _free_x(base, mid, taken, fallback=None):
    """First x near base that crosses no row in mid and keeps _NEAR from every taken x; else fallback (or base)."""
    for off in (0, 10, -10, 20, -20, 30, -30, 40, -40):
        c = base + off
        if 0 < c < W and _clear_x(c, mid) and all(abs(c - t) >= _NEAR for t in taken):
            return c
    return base if fallback is None else fallback


def _gap_runs(p, g):
    """(run lo, run hi, [(stub x, +1 down / -1 up)]) of the arrow's horizontal run in gap g."""
    da = 1 if p["sa"] == "top" else -1      # leaving the top of a box below the gap: the stub hangs down
    db = 1 if p["sb"] == "top" else -1
    if p["xv"] is None:
        xf, xt, st = p["xa"], p["xb"], [(p["xa"], da), (p["xb"], db)]
    else:
        dv = 1 if p["rj"] > p["ri"] else -1
        if g == p["gaps"][0]:
            xf, xt, st = p["xa"], p["xv"], [(p["xa"], da), (p["xv"], dv)]
        else:
            xf, xt, st = p["xv"], p["xb"], [(p["xv"], -dv), (p["xb"], db)]
    return min(xf, xt), max(xf, xt), st


def _order(g, ks, plan, brief):
    """Lane order in one gap with the fewest stub-over-run and stub-over-label crossings (insertion + adjacent swaps)."""
    info = {}
    for k in ks:
        lo, hi, st = _gap_runs(plan[k], g)
        lab = (brief["arrows"][k].get("label") or "")
        p = plan[k]
        own = p["xv"] is None or max(_gap_runs(p, x)[1] - _gap_runs(p, x)[0] for x in p["gaps"]) == hi - lo
        hw = (_text_w(lab) // 2 + 4) if lab and own else 0
        c = (lo + hi) // 2
        info[k] = (lo, hi, st, c - hw, c + hw)

    def cost(a, b):   # a in the lane above b: a's down stubs cross b, b's up stubs cross a
        A, B = info[a], info[b]
        n = 0
        for x, d in A[2]:
            if d > 0:
                n += (B[0] < x < B[1]) + 2 * (B[3] < x < B[4])
        for x, d in B[2]:
            if d < 0:
                n += (A[0] < x < A[1]) + 2 * (A[3] < x < A[4])
        return n

    order = []
    for k in ks:
        best = min(range(len(order) + 1), key=lambda i: (sum(cost(o, k) for o in order[:i]) + sum(cost(k, o) for o in order[i:]), i))
        order.insert(best, k)
    moved = True
    while moved:
        moved = False
        for i in range(len(order) - 1):
            if cost(order[i + 1], order[i]) < cost(order[i], order[i + 1]):
                order[i], order[i + 1] = order[i + 1], order[i]
                moved = True
    return order


def _geom(brief):
    """(pos, bands, H, lane ys per gap, plan, gaps) — gaps between rows grow to hold one lane per arrow using them."""
    grid = _grid(brief)
    plan, gaps = _plan(brief, grid)

    def need(g):
        return LANE * len(gaps[g]) + LANE_PAD if gaps[g] else 0

    def lanes_at(g, top):
        return [top + LANE_TOP + LANE * i for i in range(len(gaps[g]))]

    pos, bands, lane_y = {}, [], [[] for _ in gaps]
    lane_y[0] = lanes_at(0, 0)
    y, gi, bottom = max(PAD, need(0)), 0, PAD
    for b, rows in grid:
        top, ry = y, y + BAND_HEAD
        for r, row in enumerate(rows):
            if r:
                lane_y[gi] = lanes_at(gi, ry)
                ry += max(GAP_Y, need(gi))
            for bid, x, w in row:
                pos[bid] = (x, ry, w, BOX_H)
            ry += BOX_H
            gi += 1
        if not rows:
            ry += BOX_H
        bottom = ry + 16
        bands.append((b, top, bottom - top))
        if rows:   # inter-band lanes live in the white space between band rects, clear of the band labels
            lane_y[gi] = lanes_at(gi, bottom)
            y = bottom + max(BAND_GAP, need(gi))
        else:
            y = bottom + BAND_GAP
    H = max([bottom + PAD] + [ly + 8 for ys in lane_y for ly in ys])
    return pos, bands, H, lane_y, plan, gaps


def layout(brief):
    """{box id: (x, y, w, h)}, [(band, y, h)], total height — pure, integers only."""
    return _geom(brief)[:3]


def _clear_x(x, rows):
    """x crosses no box of the rows, nor the band title of a row that is first in its band (row[3])."""
    return all(not (r[0] <= x <= r[0] + r[2]) for row in rows for r in row[2]) and \
        all(not (row[3][0] <= x <= row[3][1]) for row in rows if len(row) > 3 and row[3])


def _lane_x(x1, x2, mid_rows):
    """Vertical lane x that crosses no box of the rows in between: box mid-points first, else a column gap or margin."""
    cands = [x1, x2, PAD // 2, W - PAD // 2]
    for row in mid_rows:
        rs = row[2]
        if len(row) > 3 and row[3]:
            cands.append(row[3][1] + 4)
        cands.append((PAD + rs[0][0]) // 2)
        cands.append((rs[-1][0] + rs[-1][2] + W - PAD) // 2)
        cands.extend((p[0] + p[2] + q[0]) // 2 for p, q in zip(rs, rs[1:]))
    ok = [x for x in cands if _clear_x(x, mid_rows)]
    return min(ok, key=lambda x: (abs(x - x1) + abs(x - x2), x))


def _hit(a, c):
    return a[0] < c[0] + c[2] and c[0] < a[0] + a[2] and a[1] < c[1] + c[3] and c[1] < a[1] + a[3]


def _spans(p, lane, k):
    """[(lane y, x from, x to)] — the arrow's horizontal runs, one per gap it uses (⚠never straight across a row)."""
    ls = [lane[(g, k)] for g in p["gaps"]]
    if p["xv"] is None:
        return [(ls[0], p["xa"], p["xb"])]
    return [(ls[0], p["xa"], p["xv"]), (ls[1], p["xv"], p["xb"])]


def routes(brief):
    """{arrow index: (points, d, label x, label y)} for the arrows that are drawn — pure, for the figure and tests.
    Each arrow owns one lane per gap it crosses, so runs and labels in one gap never share a y."""
    pos, bands, _h, lane_y, plan, gaps = _geom(brief)
    arrows = brief.get("arrows") or []
    lane = {(g, k): lane_y[g][i] for g, ks in enumerate(gaps) for i, k in enumerate(ks)}
    pts, verts = {}, []
    for k, p in plan.items():
        a, b = pos[arrows[k]["from"]], pos[arrows[k]["to"]]
        y1 = a[1] if p["sa"] == "top" else a[1] + a[3]
        y2 = b[1] if p["sb"] == "top" else b[1] + b[3]
        raw = [(p["xa"], y1)]
        for ly, xf, xt in _spans(p, lane, k):
            raw += [(xf, ly), (xt, ly)]
        raw.append((p["xb"], y2))
        out = [raw[0]]
        for q in raw[1:]:
            if q != out[-1]:
                out.append(q)
        pts[k] = out
        verts += [(k, q[0], min(q[1], r[1]), max(q[1], r[1])) for q, r in zip(out, out[1:]) if q[0] == r[0]]
    horiz = [(k, min(q[0], r[0]), max(q[0], r[0]), q[1]) for k, out in pts.items() for q, r in zip(out, out[1:]) if q[1] == r[1]]
    titles = [(PAD + 16, y + 8, _title_w(b["name"]), 15) for b, y, _bh in bands]
    placed, boxes, res = [], list(pos.values()), {}

    def score(k, r):
        return (1000 * sum(_hit(r, o) for o in placed + boxes) + 50 * sum(_hit(r, t) for t in titles)
                + sum(1 for kk, x, ya, yb in verts if kk != k and r[0] < x < r[0] + r[2] and ya < r[1] + r[3] and r[1] < yb)
                + sum(1 for kk, xa, xb, y in horiz if kk != k and r[1] < y < r[1] + r[3] and xa < r[0] + r[2] and r[0] < xb))

    for k in sorted(plan):
        label = arrows[k].get("label")
        lw = _text_w(label) if label else 0
        spans = sorted(_spans(plan[k], lane, k), key=lambda s: -abs(s[2] - s[1]))
        ly, xf, xt = spans[0]
        best = (0, (xf + xt) // 2, ly - 5, None)
        if label:
            best = None
            # Longest run first; slide along it (the label may hang past a short run's ends but stays over it).
            for ly, xf, xt in spans:
                lo, hi = min(xf, xt), max(xf, xt)
                c, reach = (lo + hi) // 2, (hi - lo) // 2 + max(0, lw // 2 - 8)
                cands = [c]
                for s in range(6, reach + 1, 6):
                    cands += [c + s, c - s]
                for cx in cands:
                    cx = min(max(cx, PAD // 2 + lw // 2), W - PAD // 2 - lw // 2)
                    r = (cx - lw // 2, ly - 15, lw, 13)
                    sc = score(k, r)
                    if best is None or sc < best[0]:
                        best = (sc, cx, ly - 5, r)
                    if sc == 0:
                        break
                if best[0] == 0:
                    break
            # ⚠No free spot over a run (crossing stubs span the whole gap height, so a taller gap frees nothing):
            # set the label beside one of the arrow's own vertical segments instead.
            if best[0]:
                for kk, x, ya, yb in verts:
                    if kk != k:
                        continue
                    for top in range(ya + 2, yb - 14, 4):
                        for rx in (x + 4, x - 4 - lw):
                            r = (rx, top, lw, 13)
                            sc = score(k, r)
                            if sc < best[0] and 0 < rx and rx + lw < W:
                                best = (sc, rx + lw // 2, top + 10, r)
            placed.append(best[3])
        out = pts[k]
        d = "M%d,%d " % out[0] + " ".join("L%d,%d" % x for x in out[1:])
        res[k] = (out, d, best[1], best[2])
    return res


def figure(brief):
    pos, bands, H = layout(brief)
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, e(brief.get("title"))),
           '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#475569"/></marker></defs>']
    for k, (b, y, h) in enumerate(bands):
        out.append('<g data-band="%s"><rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="#f1f5f9" stroke="#94a3b8"/>'
                   '<text x="%d" y="%d" class="t-band">%s</text></g>' % (e(b["id"]), PAD, y, W - 2 * PAD, h, PAD + 16, y + 20,
                                                                         e(b["name"])))
    band_ix = {b["id"]: k for k, b in enumerate(brief["bands"])}
    for x in brief["boxes"]:
        bx, by, bw, bh = pos[x["id"]]
        stroke, fill = PALETTE[band_ix.get(x["band"], 0) % len(PALETTE)]
        ids = " ".join(x["modules"])
        rows = ['<g data-box="%s" data-mods="%s"><title>%s</title>' % (e(x["id"]), e(ids), e(x["name"] + " — " + ids)),
                '<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="%s" stroke="%s" stroke-width="1.4"/>'
                % (bx, by, bw, bh, fill, stroke)]
        ty = by + 22
        for ln in _wrap2(x["name"], bw - 20, 14):
            rows.append('<text x="%d" y="%d" class="t-title">%s</text>' % (bx + 10, ty, e(ln)))
            ty += 17
        if x.get("note"):
            rows.append('<text x="%d" y="%d" class="t-sub">%s</text>' % (bx + 10, ty, e(_fit(x["note"], bw - 20, 12))))
        rows.append('<text x="%d" y="%d" class="t-ids">%s</text></g>' % (bx + 10, by + bh - 9, e(_fit(ids, bw - 20, 10))))
        out.extend(rows)
    rt = routes(brief)
    for k, a in enumerate(brief.get("arrows") or []):
        if k not in rt:
            continue
        _pts, d, lx, ly = rt[k]
        g = '<g data-arrow="%s %s" data-edges="%s"><path d="%s" class="edge" marker-end="url(#arr)"/>' % (
            e(a["from"]), e(a["to"]), e(" ".join(str(i) for i in a["edges"])), d)
        if a.get("label"):
            g += '<text x="%d" y="%d" class="t-edge" text-anchor="middle">%s</text>' % (lx, ly, e(a["label"]))
        out.append(g + "</g>")
    out.append("</svg>")
    return "\n".join(out)


def table(brief):
    r = brief.get("route") or {}
    names = {x["id"]: x["name"] for x in brief["boxes"]}
    out = []
    if "na" in r:
        out.append('<table><tr><td>%s</td></tr></table>' % e(r["na"] or "Not applicable"))
        return "\n".join(out)
    if r.get("by"):
        out.append('<p class="by">%s</p>' % e(r["by"]))
    out.append("<table><thead><tr><th>#</th><th>When</th><th>Goes to</th><th>Box</th><th>Evidence</th></tr></thead><tbody>")
    for k, row in enumerate(r.get("rows") or [], 1):
        ev = row.get("evidence") or {}
        out.append('<tr><td class="n">%d</td><td>%s</td><td>%s</td><td>%s</td><td class="ev">%s:%s</td></tr>' % (
            k, e(row.get("when")), e(row.get("goes")), e(names.get(row.get("box"), "")), e(ev.get("file")), e(ev.get("line"))))
    out.append("</tbody></table>")
    return "\n".join(out)


def render(brief):
    """brief.html text for a gate-checked brief (see sidereus/arch_brief.py for the schema)."""
    heads = brief.get("heads") or {}
    c7 = str(brief.get("commit") or "")[:7]
    return "\n".join([
        "<!doctype html>", '<html><head><meta charset="utf-8">',
        "<title>%s</title>" % e(brief.get("title")), "<style>%s</style>" % CSS, "</head><body><main>",
        "<h1>%s</h1>" % e(brief.get("title")), '<p class="lead">commit %s</p>' % e(c7),
        '<section class="arch"><h2>%s</h2><div class="fig">' % e(heads.get("arch") or "Architecture"),
        figure(brief), "</div></section>",
        '<section class="route"><h2>%s</h2>' % e(heads.get("route") or "Decision order"),
        table(brief), "</section>", "</main></body></html>", ""])
