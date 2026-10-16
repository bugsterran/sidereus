"""Demo Structure data (split out of sidereus/demo.py for the size cap): demo_arch / demo_src / demo_tree / demo_file."""
from sidereus.arch_verify import render_md


# ── synthetic shop repo: a small Java + Go + Python source set (source popup, file tree, arch evidence) ──
REL_ROOT = "/home/demo/src/shop"
REL_SRC = {
    "order/OrderRepository.java": "package shop.order;\n\npublic interface OrderRepository {\n"
        "    Order findById(long id);\n    void save(Order order);\n}\n",
    "order/JpaOrderRepository.java": "package shop.order;\n\n@Repository\npublic class JpaOrderRepository implements OrderRepository {\n"
        "    private final EntityManager em;\n\n    public Order findById(long id) { return em.find(Order.class, id); }\n"
        "    public void save(Order order) { em.persist(order); }\n}\n",
    "common/BaseEntity.java": "package shop.common;\n\npublic abstract class BaseEntity {\n"
        "    protected long id;\n    protected long createdAt;\n\n    public long getId() { return id; }\n}\n",
    "order/Order.java": "package shop.order;\n\npublic class Order extends BaseEntity {\n"
        "    private OrderStatus status;\n    private long total;\n\n    public OrderStatus getStatus() { return status; }\n}\n",
    "order/OrderStatus.java": "package shop.order;\n\npublic enum OrderStatus {\n    NEW, PAID, SHIPPED, CANCELLED\n}\n",
    "order/OrderService.java": "package shop.order;\n\n@Service\npublic class OrderService {\n"
        "    private final OrderRepository repo;\n\n    public Order place(Order o) { repo.save(o); return o; }\n"
        "    public Order find(long id) { return repo.findById(id); }\n}\n",
    "web/OrderController.java": "package shop.web;\n\n@Controller\npublic class OrderController {\n"
        "    private final OrderService service;\n\n    public Order get(long id) { return service.find(id); }\n}\n",
    "pay/gateway.go": "package pay\n\ntype Gateway interface {\n\tCharge(amount int64) error\n}\n\n"
        "type CardGateway struct {\n\tkey string\n}\n\nfunc (g *CardGateway) Charge(amount int64) error {\n\treturn nil\n}\n",
    "app/api.py": "from app import service\n\n\ndef get_order(oid):\n    return service.find(oid)\n",
    "app/service.py": "from app import store\n\n\ndef find(oid):\n    return store.load(oid)\n",
    "app/store.py": "from app.models import OrderModel\n\n\ndef load(oid):\n    return OrderModel(oid)\n",
    "app/models.py": "class Model:\n    pass\n\n\nclass OrderModel(Model):\n    def __init__(self, oid):\n        self.oid = oid\n",
}
def _ln(f, needle):
    """1-based line of the first line of REL_SRC[f] containing `needle` (evidence lines stay true to the demo source)."""
    return next((k + 1 for k, x in enumerate(REL_SRC[f].split("\n")) if needle in x), 1)


def _ev(f, sym, needle=None):
    return {"file": f, "line": _ln(f, needle or sym), "symbol": sym}


_ARCH_COMMIT = "4f1c2a9e7b3d5c8a0e6f2b1d9c7a5e3f1b0d8c6a"
# v2 layers follow arch_schema.ROLE_LAYER. ⚠`db` stays external with no `ext` (reproduces an untyped external).
_ARCH_MODS = [{"id": "web", "name": "web", "path": "web/", "kind": "module", "role": "web", "layer": "api"},
              {"id": "order", "name": "order", "path": "order/", "kind": "module", "role": "service", "layer": "service"},
              {"id": "common", "name": "common", "path": "common/", "kind": "module", "role": "domain", "layer": "domain"},
              {"id": "pay", "name": "pay", "path": "pay/", "kind": "module", "role": "adapter", "layer": "infra"},
              {"id": "app", "name": "app (py)", "path": "app/", "kind": "module", "role": "web", "layer": "api"},
              {"id": "db", "name": "PostgreSQL", "path": "", "kind": "external"}]
# (from, to, kind, label, evidence, verified) — one unverified edge so the rate is not a flat 100 %
_ARCH_EDGES = [("web", "order", "call", "find order", [_ev("web/OrderController.java", "service.find")], True),
               ("order", "common", "import", "extends BaseEntity", [_ev("order/Order.java", "BaseEntity")], True),
               ("order", "db", "config", "JPA repository", [_ev("order/JpaOrderRepository.java", "@Repository")], True),
               ("order", "pay", "di", "card gateway", [_ev("pay/gateway.go", "Gateway", "type Gateway")], True),
               ("app", "order", "call", "order lookup", [_ev("app/service.py", "store.load")], False)]
# (id, name, entry kind, entry label, [(from, to, label, evidence, ok, why)]) — flow 2 has one unproven step
_ARCH_FLOWS = [("get-order", "Get an order", "http", "GET /orders/{id}",
                [("web", "order", "find(id)", _ev("web/OrderController.java", "service.find"), True, None),
                 ("order", "db", "findById", _ev("order/JpaOrderRepository.java", "em.find"), True, None)]),
               ("pay-order", "Pay for an order", "http", "POST /orders/{id}/pay",
                [("web", "order", "place(order)", _ev("order/OrderService.java", "place"), True, None),
                 ("order", "pay", "charge", _ev("order/OrderService.java", "gateway.charge", "repo.save"), False,
                  "nosym")])]


def demo_arch(now):
    """Body of demo `GET /api/arch` — same keys as arch_map.load(); fake shop map, never a real repo."""
    m = {"modules": _ARCH_MODS, "edges": [{"from": a, "to": b, "kind": k, "label": lab, "evidence": ev}
                                          for a, b, k, lab, ev, _ok in _ARCH_EDGES]}
    oks = [x[5] for x in _ARCH_EDGES]
    edges = [dict(e, est=1 if e["kind"] in ("config", "di") else 0, ok=ok) for e, ok in zip(m["edges"], oks)]
    flows = [{"id": i, "name": n, "entry": {"kind": k, "label": lab},
              "ok": all(s[4] for s in st),
              "steps": [{"from": a, "to": b, "label": sl, "est": 0, "ok": ok, "why": why, "evidence": ev}
                        for a, b, sl, ev, ok, why in st]} for i, n, k, lab, st in _ARCH_FLOWS]
    return {"ok": True, "empty": False, "sidereus": "", "commit": _ARCH_COMMIT, "head": _ARCH_COMMIT, "stale": False,
            "behind": None, "at": now - 7200, "v": 2, "groups": [], "modules": _ARCH_MODS, "edges": edges,
            "rate": round(sum(oks) / float(len(oks)), 2),
            "md": render_md(m, {"edges": [{"i": i, "ok": ok} for i, ok in enumerate(oks)]}),
            "style": {"style": "layered", "framework": "Spring Boot", "units": "top-level packages",
                      "evidence": [{"file": "pom.xml", "ok": True}, {"file": "web/OrderController.java", "ok": True}],
                      "ok": True},
            "dev": [], "flows": flows, "checks": _demo_checks(now)}


# (tool, file, line, rule, sev, pkg) — security results on the shop modules (no secrets, metadata only)
_SEC_ITEMS = [("gitleaks", "app/store.py", 3, "generic-api-key", "error", None),
              ("bandit", "app/api.py", 4, "B105", "warning", None),
              ("bandit", "app/service.py", 6, "B608", "warning", None),
              ("osv-scanner", "pay/gateway.go", 1, "GHSA-qppj-fm5r-hxr3", "warning", "golang.org/x/net")]


def _demo_checks(now):
    """Demo `checks` (same keys as arch_checks.load_checks): empty top-level shell + `security` with a short history."""
    mods, n = {}, {}
    for t, f, _ln, _r, sev, _p in _SEC_ITEMS:
        mods.setdefault(f.split("/", 1)[0], {"error": 0, "warning": 0})[sev] += 1
        n.setdefault(t, {"error": 0, "warning": 0})[sev] += 1
    z = {"error": 0, "warning": 0}
    tools = [{"id": "gitleaks", "rules": "default", "status": "ok", "ms": 900, "files": 64, "n": n["gitleaks"]},
             {"id": "osv-scanner", "rules": "default", "status": "ok", "ms": 2100, "files": 2, "n": n["osv-scanner"]},
             {"id": "bandit", "rules": "default", "status": "ok", "ms": 700, "files": 4, "n": n["bandit"]},
             {"id": "semgrep", "rules": "project", "status": "missing", "why": "install: brew install semgrep", "ms": 0,
              "files": 0, "n": z}]
    rules = {"bandit:B105": {"desc": "hardcoded password string", "url": "https://bandit.readthedocs.io/en/latest/plugins/b105_hardcoded_password_string.html"},
             "osv-scanner:GHSA-qppj-fm5r-hxr3": {"desc": "", "url": "https://github.com/advisories/GHSA-qppj-fm5r-hxr3"}}
    top = [dict({"tool": t, "file": f, "line": ln, "rule": r, "sev": sev, "mod": f.split("/", 1)[0],
                 "rk": t + ":" + r if t + ":" + r in rules else ""}, **({"pkg": pk} if pk else {}))
           for t, f, ln, r, sev, pk in _SEC_ITEMS]
    at = now - 3600

    def row(sev, f, ln, key, desc, src, status):
        return {"sev": sev, "file": f, "line": ln, "key": key, "desc": desc, "src": src, "ai": src == "review",
                "status": status, "at": at, "commit": _ARCH_COMMIT}
    log = {"at_scan": at, "at_review": at - 600,
           "open": [row("error", "app/store.py", 3, "gitleaks:generic-api-key", "generic-api-key", "scan", "open"),
                    row("high", "app/api.py", 9, "missing-authz", "Order lookup does not check the caller owns the order",
                        "review", "open")],
           "resolved": [row("warning", "app/models.py", 2, "bandit:B311", "B311", "scan", "resolved")], "fp": []}
    sec = {"commit": _ARCH_COMMIT, "at": at, "stale": False, "dirty": False, "src_changed": False, "tools": tools,
           "mods": mods, "other": dict(z), "top": top, "rules": rules, "log": log}
    return {"commit": "", "at": None, "stale": False, "dirty": False, "src_changed": False, "tools": [], "mods": {},
            "other": dict(z), "top": [], "rules": {}, "security": sec}


def demo_src(path="", file="", line="1", lines="0"):
    """Body of demo `GET /api/structure/src` — a synthetic file from REL_SRC, same keys as structure_src()."""
    text = REL_SRC.get(file)
    if text is None:
        return {"ok": False, "msg": "This path cannot be read."}
    try:
        a, n = max(1, int(line)), max(1, min(int(lines or 0) or 40, 100000))
    except (TypeError, ValueError):
        return {"ok": False, "msg": "Invalid range."}
    all_l = text.split("\n")
    seg = all_l[a - 1:a - 1 + n]
    ext = file.rsplit(".", 1)[-1]
    return {"ok": True, "path": path if path.startswith("/home/demo/") else REL_ROOT, "file": file, "src": "cur",
            "rev": "", "at": 0, "line": a, "from": a, "n": len(seg), "want": n, "total": len(all_l), "exact": True,
            "note": "", "truncated": False, "code": "\n".join(seg), "lang": ext, "warm": False}


def _jv(pkg, head):
    return "package shop.%s;\n\n%s {\n    // demo stub\n}\n" % (pkg, head)


# «Structure» file tree: REL_SRC (so arch evidence opens) + invented extras; None = locked (.env), int = binary size
_TREE_SRC = dict(REL_SRC, **{
    "README.md": "# shop\n\nDemo storefront: Java order core, Go payments, Python API, TS web.\n\n## Layout\n\n"
        "| Part | Where |\n|---|---|\n| Orders | [OrderService](order/OrderService.java) |\n| Payments | `pay/` |\n\n"
        "## Run\n\n```sh\nmvn -q test\n```\n\n- Docs: [example.com](https://example.com/shop)\n- **Config** in `config/application.yml`\n",
    "pom.xml": "<project>\n  <groupId>shop</groupId>\n  <artifactId>shop-core</artifactId>\n</project>\n",
    "go.mod": "module shop/pay\n\ngo 1.22\n", ".gitignore": "target/\nnode_modules/\n.env\n", ".env": None,
    "docs/logo.png": 2048, "config/application.yml": "server:\n  port: 8080\nspring:\n  jpa:\n    open-in-view: false\n",
    "order/OrderMapper.java": _jv("order", "public final class OrderMapper"),
    "order/OrderEvent.java": _jv("order", "public record OrderEvent(long orderId, OrderStatus status)"),
    "common/Money.java": _jv("common", "public final class Money"),
    "web/HealthController.java": _jv("web", "@Controller\npublic class HealthController"),
    "pay/gateway_test.go": "package pay\n\nimport \"testing\"\n\nfunc TestCharge(t *testing.T) {\n"
        "\tif err := (&CardGateway{}).Charge(100); err != nil {\n\t\tt.Fatal(err)\n\t}\n}\n",
    "app/__init__.py": "", "tests/test_service.py": "from app import service\n\n\ndef test_find():\n"
        "    assert service.find(1).oid == 1\n",
    "ui/package.json": "{\n  \"name\": \"shop-ui\",\n  \"private\": true\n}\n",
    "ui/tsconfig.json": "{\n  \"compilerOptions\": { \"strict\": true }\n}\n",
    "ui/src/api.ts": "export async function getOrder(id: number): Promise<Order> {\n"
        "  const r = await fetch(`/api/orders/${id}`);\n  return r.json();\n}\n",
    "ui/src/format.ts": "export const won = (n: number): string => n.toLocaleString('ko-KR') + '원';\n",
    "ui/src/OrderList.tsx": "import { won } from './format';\n\nexport function OrderList({ items }: Props) {\n"
        "  return <ul>{items.map(o => <li key={o.id}>{won(o.total)}</li>)}</ul>;\n}\n",
})


# demo git state per file (A added / M modified / D deleted — D rows are not in _TREE_SRC and do not open)
_TREE_ST = {"order/OrderEvent.java": "A", "ui/src/format.ts": "A", "README.md": "M", "pay/gateway_test.go": "M",
            "config/application.yml": "M", "order/LegacyOrderDao.java": "D"}


def _root(path):
    return path if (path or "").startswith("/home/demo/") else REL_ROOT


def demo_tree(path=""):
    """Body of demo `GET /api/structure/tree` — same keys as structure_tree.structure_tree()."""
    fs, stn = [], {"A": 0, "M": 0, "D": 0}
    for p in sorted(set(_TREE_SRC) | set(_TREE_ST)):
        v = _TREE_SRC.get(p, 0)
        e = {"p": p, "sz": v if isinstance(v, int) else len((v or "KEY=demo\n").encode())}
        if v is None:
            e["sec"] = 1
        if p in _TREE_ST:
            e["st"] = _TREE_ST[p]
            stn[e["st"]] += 1
        fs.append(e)
    return {"ok": True, "path": _root(path), "git": True, "files": fs, "n": len(fs), "truncated": False, "warm": True,
            "stn": stn}


def demo_file(path="", file="", line="1"):
    """Body of demo `GET /api/structure/file` — same keys as structure_tree.structure_file()."""
    if _TREE_ST.get(file) == "D":
        return {"ok": False, "msg": "This file was deleted.", "gone": True}
    if file not in _TREE_SRC:
        return {"ok": False, "msg": "This file is not in the list."}
    v = _TREE_SRC[file]
    if v is None:
        return {"ok": False, "locked": True, "msg": "This file cannot be opened."}
    if isinstance(v, int):
        return {"ok": False, "bin": True, "bytes": v, "msg": "This is a binary file."}
    ls = v.split("\n")
    return {"ok": True, "path": _root(path), "file": file, "line": min(max(1, _int1(line)), len(ls)),
            "n": len(ls), "code": v, "truncated": False, "bytes": len(v.encode()), "enc": "utf-8", "masked": 0, "note": ""}



def _int1(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return 1
