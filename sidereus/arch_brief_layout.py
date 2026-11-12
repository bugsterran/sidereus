"""Overview (arch-brief) v2 hand layout: an optional brief.json `layout` placed by the session that drew the brief.

shape_errors / geom_errors check the coordinates (called by arch_brief._gate after the v2 checks pass); figure draws the
containment svg with exactly those numbers. Without `layout` arch_brief_html_v2's automatic layout stays.
Pure and stdlib only; numbers only — every text drawn comes from the gate-checked brief, through e().
"""
from sidereus.arch_schema import _int
from sidereus.arch_brief_html import e, _text_w
from sidereus.arch_brief_html_v2 import (GRP_H, GRP_HEAD, IN_W, PKG_GX, PKG_H, PR_LINE, _actor_w, _box, _d, _ext, _ext_text,
                                         _fit_lines, _group, _hit, _principle)

W_MIN, W_MAX, H_MIN, H_MAX = 600, 2400, 300, 3000
PTS_MIN, PTS_MAX = 2, 8
LABEL_H = 13              # arrow label box: _text_w(label) x LABEL_H centred on its [x, y] (the 11px .t-edge text)
BOX_MIN_W, PKG_MIN_W, ACTOR_MIN_H = 60, 40, 20
SYS = "system"
LIST_MAX = 5              # ids named per «missing»/«unknown» error

FORMAT = """layout? (optional; without it the figure is laid out automatically) — integers only, 0..W / 0..H:
  {size:[W %d..%d, H %d..%d], boxes:{<id>:[x, y, w, h]} for exactly every actor, screen, component and external id plus "system",
   arrows:[{pts:[[x, y]] %d..%d, label:[x, y]}] (same length and order as arrows), principles:[x, y]}
label [x, y] = centre of a box as wide as the label text and %d px high; principles [x, y] = top-left of a block %d px wide,
%d px per line. Refused: overlapping boxes; a component outside "system"; an actor, screen or external touching "system";
an arrow whose first/last point is not on the border of its from/to box; a label over a box, a line or another label;
anything outside the figure; a box too small for its text; the principles block outside "system" or over a component.
""" % (W_MIN, W_MAX, H_MIN, H_MAX, PTS_MIN, PTS_MAX, LABEL_H, IN_W, PR_LINE)

MARKER = ('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
          'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#475569"/></marker></defs>')


def leaves(b):
    """[(id, kind, item)] of every drawn box but the system container, in drawing order."""
    return ([(a["id"], "actor", a) for a in b["actors"]] + [(x["id"], "screen", x) for x in b["screens"]]
            + [(c["id"], "component", c) for c in b["system"]["components"]] + [(x["id"], "external", x) for x in b["externals"]])


def _n(x, hi):
    return _int(x) and 0 <= x <= hi


def _xy(p, w, h):
    return isinstance(p, list) and len(p) == 2 and _n(p[0], w) and _n(p[1], h)


def _tag(b, k):
    return "arrow %d %s->%s" % (k + 1, b["arrows"][k]["from"], b["arrows"][k]["to"])


def shape_errors(lay, b):
    """Type, key and range errors of `layout` for a gate-checked v2 brief b. Caps refuse, never clamp."""
    if not isinstance(lay, dict) or set(lay) != {"size", "boxes", "arrows", "principles"}:
        return ["layout: {size, boxes, arrows, principles}"]
    s = lay["size"]
    if not (isinstance(s, list) and len(s) == 2 and _int(s[0]) and _int(s[1]) and W_MIN <= s[0] <= W_MAX
            and H_MIN <= s[1] <= H_MAX):
        return ["layout size: [W %d..%d, H %d..%d] integers" % (W_MIN, W_MAX, H_MIN, H_MAX)]
    w, h = s
    errs, bx = [], lay["boxes"]
    want = set(x[0] for x in leaves(b)) | {SYS}
    if not isinstance(bx, dict):
        errs.append("layout boxes: {id: [x, y, w, h]}")
    else:
        for what, ids in (("missing", want - set(bx)), ("unknown", set(bx) - want)):
            if ids:
                errs.append("layout boxes: %s %s" % (what, ", ".join(sorted(i[:40] for i in ids)[:LIST_MAX])))
        for k in sorted(want & set(bx)):
            v = bx[k]
            if not (isinstance(v, list) and len(v) == 4 and _n(v[0], w) and _n(v[1], h) and _n(v[2], w) and _n(v[3], h)):
                errs.append("layout box %s: [x, y, w, h] integers within %dx%d" % (k, w, h))
    ar = lay["arrows"]
    if not isinstance(ar, list) or len(ar) != len(b["arrows"]):
        errs.append("layout arrows: one {pts, label} per arrow in the same order (%d)" % len(b["arrows"]))
    else:
        for k, a in enumerate(ar):
            if not (isinstance(a, dict) and set(a) == {"pts", "label"} and isinstance(a["pts"], list)
                    and PTS_MIN <= len(a["pts"]) <= PTS_MAX and all(_xy(p, w, h) for p in a["pts"]) and _xy(a["label"], w, h)):
                errs.append("layout %s: {pts:[[x, y]] %d..%d, label:[x, y]} integers within %dx%d" % (_tag(b, k), PTS_MIN, PTS_MAX, w, h))
    if not _xy(lay["principles"], w, h):
        errs.append("layout principles: [x, y] integers within %dx%d" % (w, h))
    return errs


def _touch(p, q):
    """Rects overlap or share an edge or corner."""
    return p[0] <= q[0] + q[2] and q[0] <= p[0] + p[2] and p[1] <= q[1] + q[3] and q[1] <= p[1] + p[3]


def _inside(p, q):
    return q[0] <= p[0] and q[1] <= p[1] and p[0] + p[2] <= q[0] + q[2] and p[1] + p[3] <= q[1] + q[3]


def _on_border(pt, r):
    x, y = pt
    return (r[0] <= x <= r[0] + r[2] and y in (r[1], r[1] + r[3])) or (r[1] <= y <= r[1] + r[3] and x in (r[0], r[0] + r[2]))


def _seg_in(q, r, rect):
    """Segment q-r passes through the interior of rect (Liang-Barsky clip; a line along an edge or a corner touch is clear)."""
    dx, dy = r[0] - q[0], r[1] - q[1]
    t0, t1 = 0.0, 1.0
    for p, d in ((-dx, q[0] - rect[0]), (dx, rect[0] + rect[2] - q[0]), (-dy, q[1] - rect[1]), (dy, rect[1] + rect[3] - q[1])):
        if p == 0:
            if d < 0:
                return False
        elif p < 0:
            t0 = max(t0, d / float(p))
        else:
            t1 = min(t1, d / float(p))
    if t0 > t1:
        return False
    tm = (t0 + t1) / 2
    mx, my = q[0] + dx * tm, q[1] + dy * tm
    return rect[0] < mx < rect[0] + rect[2] and rect[1] < my < rect[1] + rect[3]


def label_rect(b, lay, k):
    w = _text_w(b["arrows"][k]["label"])
    x, y = lay["arrows"][k]["label"]
    return (x - w // 2, y - LABEL_H // 2, w, LABEL_H)


def _prin_lines(b):
    return [_principle(p)[0] for p in b["system"]["principles"]]


def prin_rect(b, lay):
    x, y = lay["principles"]
    return (x, y, IN_W, PR_LINE * sum(len(t) for t in _prin_lines(b)) + 6)


def _ext_rows(x, r):
    """(use row centres, needed height) of an external drawn at r — the same arithmetic as arch_brief_html_v2._geom."""
    head, uses = _ext_text(x)
    hh = 12 + (head[1] + 3) * len(head[0])
    rhs = [6 + (u[1] + 3) * len(u[0]) for u in uses]
    return [r[1] + hh + sum(rhs[:i]) + rhs[i] // 2 for i in range(len(rhs))], hh + sum(rhs) + 6


def _sys_title(b, r):
    """Rect of the system name (15px bold at x + 16, baseline y + 22)."""
    return (r[0] + 16, r[1] + 6, int(_text_w(b["system"]["name"]) * 15 / 11), 22)


def _widest(fits):
    return max([int(_text_w(t) * size / 11.0) for lines, size in fits for t in lines] or [0])


def _need(kind, x, r, b):
    """«needs ...» when r is too small for the text drawn in it, else ""."""
    bw, bh = r[2], r[3]
    if kind == "actor":
        nw, nh = _actor_w(x["name"]), ACTOR_MIN_H
    elif kind == "system":
        nw, nh = _sys_title(b, r)[2] + 32, 34
    elif kind == "external":
        head, uses = _ext_text(x)
        nw, nh = max(_widest([head]) + 20, _widest(uses) + 24), _ext_rows(x, r)[1]
    elif "pkgs" in x:
        n = len(x["pkgs"])
        pw = (bw - 20 - (n - 1) * PKG_GX) // n
        fits = [_fit_lines(p["name"], pw - 16, 14, 2) for p in x["pkgs"]] if pw >= PKG_MIN_W else []
        ok = pw >= PKG_MIN_W and bh >= GRP_H and len(_fit_lines(x["name"], bw - 20, 14, 1)[0]) == 1 \
            and all((f[1] + 3) * len(f[0]) + 4 <= PKG_H for f in fits)
        return "" if ok else "needs h >= %d, a one-line name and package boxes >= %d px wide holding their names" % (GRP_H, PKG_MIN_W)
    else:
        fit = _fit_lines(x["name"], bw - 20, 14, 3) if bw >= BOX_MIN_W else ([], 14)
        nw, nh = BOX_MIN_W, (fit[1] + 3) * len(fit[0]) + 10
    if bw >= nw and bh >= nh:
        return ""
    return "needs w >= %d, h >= %d" % (nw, nh)


def geom_errors(lay, b):
    """Geometry errors of a shape-valid layout; each names the box or arrow it is about."""
    w, h = lay["size"]
    fig, R = (0, 0, w, h), dict((k, tuple(v)) for k, v in lay["boxes"].items())
    sysr, lv, errs = R[SYS], leaves(b), []
    for bid, kind, x in lv + [(SYS, "system", b["system"])]:
        if not _inside(R[bid], fig):
            errs.append("layout box %s: outside the %dx%d figure" % (bid, w, h))
        need = _need(kind, x, R[bid], b)
        if need:
            errs.append("layout box %s: too small for its text (%s)" % (bid, need))
    for i, (p, _k, _x) in enumerate(lv):
        for q, _k2, _x2 in lv[i + 1:]:
            if _hit(R[p], R[q]):
                errs.append("layout box %s: overlaps %s" % (p, q))
    title = _sys_title(b, sysr)
    for bid, kind, _x in lv:
        if kind == "component" and not _inside(R[bid], sysr):
            errs.append("layout box %s: component outside system" % bid)
        elif kind != "component" and _touch(R[bid], sysr):
            errs.append("layout box %s: %s touches system (only components go inside)" % (bid, kind))
        if kind == "component" and _hit(R[bid], title):
            errs.append("layout box %s: covers the system name" % bid)
    segs = []
    for k, (a, la) in enumerate(zip(b["arrows"], lay["arrows"])):
        pts = [tuple(p) for p in la["pts"]]
        for end, pt, bid in (("first", pts[0], a["from"]), ("last", pts[-1], a["to"])):
            if not _on_border(pt, R[bid]):
                errs.append("layout %s: %s point (%d, %d) not on the border of %s" % (_tag(b, k), end, pt[0], pt[1], bid))
        segs += [(k, q, r) for q, r in zip(pts, pts[1:]) if q != r]
    labs = [label_rect(b, lay, k) for k in range(len(b["arrows"]))]
    for k, lr in enumerate(labs):
        tag = _tag(b, k)
        if not _inside(lr, fig):
            errs.append("layout %s: label outside the figure" % tag)
        errs += ["layout %s: label over box %s" % (tag, bid) for bid, _k, _x in lv if _hit(lr, R[bid])]
        over = sorted(set(k2 for k2, q, r in segs if _seg_in(q, r, lr)))
        errs += ["layout %s: label over the line of %s" % (tag, "itself" if k2 == k else _tag(b, k2)) for k2 in over]
        errs += ["layout %s: label over %s" % (tag, nm) for nm in sorted(set(nm for nm, q, r in _deco(b, lay, R) if _seg_in(q, r, lr)))]
        errs += ["layout %s: label over the label of %s" % (tag, _tag(b, k2)) for k2 in range(k + 1, len(labs)) if _hit(lr, labs[k2])]
    pr = prin_rect(b, lay)
    if not _inside(pr, sysr):
        errs.append("layout principles: block (%d, %d, %d, %d) outside system" % pr)
    errs += ["layout principles: block over component %s" % bid for bid, kind, _x in lv if kind == "component" and _hit(pr, R[bid])]
    if _hit(pr, title):
        errs.append("layout principles: block over the system name")
    return errs


def _screen_of(b, i):
    """Screen id actor i is joined to (the same pick as the automatic figure)."""
    return b["screens"][min(i, len(b["screens"]) - 1)]["id"]


def _deco(b, lay, R):
    """[(name, q, r)] of every drawn line that is not an arrow — system border, principles rule, actor connectors.
    ⚠figure draws exactly these: a label is checked against every line on the page, not only the arrows."""
    x, y, w, h = R[SYS]
    c = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    out = [("the system border", c[i], c[(i + 1) % 4]) for i in range(4)]
    px, py = lay["principles"]
    out.append(("the principles rule", (px, py + 2), (px + IN_W, py + 2)))
    for i, a in enumerate(b["actors"]):
        pts = _join(R[a["id"]], R[_screen_of(b, i)])
        out += [("the connector of actor %s" % a["id"], q, r) for q, r in zip(pts, pts[1:]) if q != r]
    return out


def _join(p, q):
    """Points of the dashed actor-to-screen connector: side to side when apart horizontally, else top/bottom."""
    if q[0] >= p[0] + p[2] or p[0] >= q[0] + q[2]:
        a, z = (p, q) if q[0] >= p[0] + p[2] else (q, p)
        y1, y2, mx = a[1] + a[3] // 2, z[1] + z[3] // 2, (a[0] + a[2] + z[0]) // 2
        return [(a[0] + a[2], y1), (mx, y1), (mx, y2), (z[0], y2)]
    a, z = (p, q) if q[1] >= p[1] + p[3] else (q, p)
    x1, x2, my = a[0] + a[2] // 2, z[0] + z[2] // 2, (a[1] + a[3] + z[1]) // 2
    return [(x1, a[1] + a[3]), (x1, my), (x2, my), (x2, z[1])]


def figure(b):
    """Containment svg drawn at the layout's coordinates (gate-checked brief with `layout`); same marks as the automatic one."""
    lay = b["layout"]
    w, h = lay["size"]
    R = dict((k, tuple(v)) for k, v in lay["boxes"].items())
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s" data-layout="1">' % (w, h, e(b["title"])), MARKER]
    for i, a in enumerate(b["actors"]):
        x, y, aw, ah = R[a["id"]]
        out.append('<g data-actor="%s"><rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="#ffffff" stroke="#64748b"/>'
                   '<text x="%d" y="%d" class="t-sub" text-anchor="middle">%s</text></g>'
                   % (e(a["id"]), x, y, aw, ah, min(12, ah // 2), x + aw // 2, y + ah // 2 + 4, e(a["name"])))
        out.append('<path class="deco" d="%s"/>' % _d(_join(R[a["id"]], R[_screen_of(b, i)])))
    for x in b["screens"]:
        out.append(_box(x, R[x["id"]], "screen", x["modules"]))
    cx, cy, cw, ch = R[SYS]
    out.append('<g data-system="1"><rect x="%d" y="%d" width="%d" height="%d" rx="14" fill="#f8fafc" stroke="#64748b" stroke-width="1.4"/>'
               '<text x="%d" y="%d" class="t-sys">%s</text></g>' % (cx, cy, cw, ch, cx + 16, cy + 22, e(b["system"]["name"])))
    for c in b["system"]["components"]:
        out.append(_group(c, R[c["id"]]) if "pkgs" in c else _box(c, R[c["id"]], "component", c["modules"]))
    px, py = lay["principles"]
    out.append('<path class="deco" d="M%d,%d L%d,%d"/>' % (px, py + 2, px + IN_W, py + 2))
    ln = 0
    for i, p in enumerate(b["system"]["principles"]):
        lines, short, full = _principle(p)
        for j, t in enumerate(lines):
            ev = '<tspan class="t-ev" dx="10"><title>%s</title>%s</tspan>' % (e(full), e(short)) if j == 0 else ""
            out.append('<text x="%d" y="%d" class="t-sub" data-principle="%d">%s%s</text>'
                       % (px + (10 if j else 0), py + 16 + PR_LINE * ln, i + 1, e(t), ev))
            ln += 1
    for x in b["externals"]:
        out.append(_ext(x, R[x["id"]], _ext_rows(x, R[x["id"]])[0]))
    for k, (a, la) in enumerate(zip(b["arrows"], lay["arrows"])):
        lx, ly = la["label"]
        out.append('<g data-arrow="%s %s" data-edges="%s"><path d="%s" class="edge" marker-end="url(#arr)"/>'
                   '<text x="%d" y="%d" class="t-edge" text-anchor="middle">%s</text></g>' % (
                       e(a["from"]), e(a["to"]), e(" ".join("%d" % i for i in a["edges"])), _d([tuple(p) for p in la["pts"]]),
                       lx, ly - LABEL_H // 2 + 11, e(a["label"])))
    out.append("</svg>")
    return "\n".join(out)
