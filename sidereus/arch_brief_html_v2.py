"""Overview (arch-brief) v2 renderer: one self-contained brief.html from a gate-checked v2 brief.json.

A containment figure (SVG, width 1200): users/screens band on top, the system container (components in rows of <= 3, one
dashed package group, design principles with file:line at the bottom), external systems with numbered uses on the right;
orthogonal labelled arrows, each owning one lane per gap it crosses. Under it a compact role table (one row per box).
Inline <style> only; no script/src/href/URL. Deterministic (input order only). ⚠No route table, sequence or package table.
"""
from sidereus.arch_brief_html import e
from sidereus.arch_brief_geom import (BAND_H, BAND_Y, GRP_HEAD, IN_L, IN_W, NUMS, PAD, PKG_GX, PKG_H, PR_LINE, W,
                                      _actor_w, _ext_text, _fit_lines, _principle, _screen_links, routes)

COLORS = {"screen": ("#2563eb", "#eff6ff"), "component": ("#059669", "#ecfdf5"), "external": ("#d97706", "#fffbeb")}

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
.fig { border: 1px solid var(--line); border-radius: 12px; overflow-x: auto; }
/* min-width keeps box text legible on phones (scrolls inside .fig); it must stay below the .fig inner width at a 900px viewport (900 - 2*16 padding - 2 border = 866) */
svg { display: block; width: 100%; min-width: 840px; max-height: 60vh; height: auto; }
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
