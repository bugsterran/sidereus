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


def layout(brief):
    """{box id: (x, y, w, h)}, [(band, y, h)], total height — pure, integers only."""
    pos, bands, y = {}, [], PAD
    for b in brief["bands"]:
        mine = [x for x in brief["boxes"] if x["band"] == b["id"]]
        n = len(mine)
        cols = max(1, n if n <= ROW_MAX else (n + 1) // 2)
        rows = max(1, (n + cols - 1) // cols)
        bw = min(BOX_W_MAX, (W - 2 * PAD - 32 - (cols - 1) * GAP_X) // cols)
        h = BAND_HEAD + rows * BOX_H + (rows - 1) * GAP_Y + 16
        for k, x in enumerate(mine):
            r, c = divmod(k, cols)
            in_row = min(cols, n - r * cols)
            left = (W - (in_row * bw + (in_row - 1) * GAP_X)) // 2
            pos[x["id"]] = (left + c * (bw + GAP_X), y + BAND_HEAD + r * (BOX_H + GAP_Y), bw, BOX_H)
        bands.append((b, y, h))
        y += h + BAND_GAP
    return pos, bands, y - BAND_GAP + PAD


def _rows(pos):
    """[(top, bottom, [box rects])] sorted top to bottom; rows never overlap vertically."""
    by = {}
    for r in pos.values():
        by.setdefault(r[1], []).append(r)
    return [(y, y + rs[0][3], sorted(rs)) for y, rs in sorted(by.items())]


def _channels(rows):
    """Horizontal lane y above row k = ch[k], below row k = ch[k + 1]; every lane lies in a gap between rows."""
    ch = [PAD // 2]
    for k in range(len(rows) - 1):
        ch.append(rows[k][1] + min(rows[k + 1][0] - rows[k][1], 2 * 21) // 2)
    ch.append(rows[-1][1] + 8)
    return ch


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


def _points(a, b, rows, ch, off):
    """Orthogonal polyline a -> b that leaves and enters at side mid-points and never crosses a box:
    side to side for neighbours in one row, else through the gaps between rows (⚠never straight across a row)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ri = [k for k, row in enumerate(rows) if row[0] == ay][0]
    rj = [k for k, row in enumerate(rows) if row[0] == by][0]
    if ri == rj:
        lo, hi = sorted((ax, bx))
        between = [r for r in rows[ri][2] if lo < r[0] < hi]
        if not between:
            x1, x2 = (ax + aw, bx) if bx >= ax else (ax, bx + bw)
            return [(x1, ay + ah // 2), (x2, ay + ah // 2)]
        y = ch[ri] + off   # around the row through the gap above it
        return [(ax + aw // 2, ay), (ax + aw // 2, y), (bx + bw // 2, y), (bx + bw // 2, by)]
    x1, x2 = ax + aw // 2, bx + bw // 2
    if rj > ri:
        y1, c1, c2, y2, mid = ay + ah, ch[ri + 1] + off, ch[rj] + off, by, rows[ri + 1:rj]
    else:
        y1, c1, c2, y2, mid = ay, ch[ri] + off, ch[rj + 1] + off, by + bh, rows[rj + 1:ri]
    if not mid:
        return [(x1, y1), (x1, c1), (x2, c1), (x2, y2)]
    xv = _lane_x(x1, x2, mid)
    return [(x1, y1), (x1, c1), (xv, c1), (xv, c2), (x2, c2), (x2, y2)]


def _route(a, b, rows, ch, k):
    """(points, d, label x, label y); arrows k spread over three lanes 4px apart so shared gaps stay readable."""
    pts = _points(a, b, rows, ch, ((k % 3) - 1) * 4)
    out = [pts[0]]
    for p in pts[1:]:
        if p != out[-1]:
            out.append(p)
    segs = [(p, q) for p, q in zip(out, out[1:]) if p[1] == q[1]] or list(zip(out, out[1:]))
    (p, q) = max(segs, key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
    d = "M%d,%d " % out[0] + " ".join("L%d,%d" % x for x in out[1:])
    return out, d, (p[0] + q[0]) // 2, (p[1] + q[1]) // 2 - 5


def routes(brief):
    """{arrow index: points} for the arrows that are drawn — pure, for the figure and tests."""
    pos = layout(brief)[0]
    rows = _rows(pos)
    ch = _channels(rows) if rows else []
    return {k: _route(pos[a["from"]], pos[a["to"]], rows, ch, k)
            for k, a in enumerate(brief.get("arrows") or []) if a["from"] in pos and a["to"] in pos and a["from"] != a["to"]}


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
