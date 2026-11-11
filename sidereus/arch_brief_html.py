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
svg { display: block; width: 100%; min-width: 900px; height: auto; }
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
td.ev { font-family: ui-monospace, Menlo, monospace; font-size: 12px; color: var(--muted); white-space: nowrap; }
.by { color: var(--muted); font-size: 13px; margin: 0 0 8px; }
"""


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def _cut(s, n):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"


def _wrap2(s, n):
    """At most two lines of ~n chars; the second is cut with an ellipsis."""
    s = str(s or "")
    if len(s) <= n:
        return [s]
    cut = s.rfind(" ", 0, n + 1)
    cut = cut if cut > n // 2 else n
    return [s[:cut].rstrip(), _cut(s[cut:].lstrip(), n)]


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


def _plan(brief, grid):
    """Per drawn arrow: rows, sides, attach x, vertical lane x; plus the arrows using each gap (gap g = above row g)."""
    where, rowlist = {}, []
    for _b, rows in grid:
        for row in rows:
            for bid, x, w in row:
                where[bid] = (len(rowlist), x, w)
            rowlist.append([(x, 0, w, 0) for _bid, x, w in row])
    rows3 = [(0, 0, r) for r in rowlist]
    gaps = [[] for _ in range(len(rowlist) + 1)]
    plan, used_xv = {}, []
    for k, a in enumerate(brief.get("arrows") or []):
        if a["from"] not in where or a["to"] not in where or a["from"] == a["to"]:
            continue
        (ri, ax, aw), (rj, bx, bw) = where[a["from"]], where[a["to"]]
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
                xv = base
                for off in (0, 10, -10, 20, -20, 30, -30):   # arrows crossing the same rows get their own vertical
                    c = base + off
                    if 0 < c < W and _clear_x(c, mid) and not any(u == c and ul < hi and lo < uh for u, ul, uh in used_xv):
                        xv = c
                        break
                used_xv.append((xv, lo, hi))
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
    for (bid, _s), lst in sides.items():
        _r, x, w = where[bid]
        lst.sort()
        for i, (_o, k, end) in enumerate(lst):
            plan[k]["xb" if end else "xa"] = x + (i + 1) * w // (len(lst) + 1)
    return plan, gaps


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
    return all(not (r[0] <= x <= r[0] + r[2]) for row in rows for r in row[2])


def _lane_x(x1, x2, mid_rows):
    """Vertical lane x that crosses no box of the rows in between: box mid-points first, else a column gap or margin."""
    cands = [x1, x2, PAD // 2, W - PAD // 2]
    for row in mid_rows:
        rs = row[2]
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
    titles = [(PAD + 16, y + 8, _text_w(b["name"]) * 13 // 11, 15) for b, y, _bh in bands]
    placed, boxes, res = [], list(pos.values()), {}
    for k in sorted(plan):
        label = arrows[k].get("label")
        lw = _text_w(label) if label else 0
        best = None
        # Longest run first; slide along it until the label meets no label, box, band title or other arrow's vertical.
        for ly, xf, xt in sorted(_spans(plan[k], lane, k), key=lambda s: -abs(s[2] - s[1])):
            lo, hi = min(xf, xt), max(xf, xt)
            c = (lo + hi) // 2
            cands = [c]
            for s in range(6, (hi - lo) // 2 + 1, 6):
                cands += [c + s, c - s]
            for cx in cands:
                cx = min(max(cx, PAD // 2 + lw // 2), W - PAD // 2 - lw // 2)
                r = (cx - lw // 2, ly - 15, lw, 13)
                score = 0
                if label:
                    score = (1000 * sum(_hit(r, o) for o in placed + boxes) + 50 * sum(_hit(r, t) for t in titles)
                             + sum(1 for kk, x, ya, yb in verts if kk != k and r[0] < x < r[0] + r[2] and ya < r[1] + r[3] and r[1] < yb))
                if best is None or score < best[0]:
                    best = (score, cx, ly, r)
                if score == 0:
                    break
            if best[0] == 0:
                break
        if label:
            placed.append(best[3])
        out = pts[k]
        d = "M%d,%d " % out[0] + " ".join("L%d,%d" % x for x in out[1:])
        res[k] = (out, d, best[1], best[2] - 5)
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
        chars = max(8, (bw - 20) // 8)
        ids = " ".join(x["modules"])
        rows = ['<g data-box="%s" data-mods="%s"><title>%s</title>' % (e(x["id"]), e(ids), e(x["name"] + " — " + ids)),
                '<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="%s" stroke="%s" stroke-width="1.4"/>'
                % (bx, by, bw, bh, fill, stroke)]
        ty = by + 22
        for ln in _wrap2(x["name"], chars):
            rows.append('<text x="%d" y="%d" class="t-title">%s</text>' % (bx + 10, ty, e(ln)))
            ty += 17
        if x.get("note"):
            rows.append('<text x="%d" y="%d" class="t-sub">%s</text>' % (bx + 10, ty, e(_cut(x["note"], chars + 4))))
        rows.append('<text x="%d" y="%d" class="t-ids">%s</text></g>' % (bx + 10, by + bh - 9, e(_cut(ids, chars + 10))))
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
