"""Static Windows-breakage scan (AST): POSIX-only calls and literals that would fail or misbehave on Windows."""
import ast
import glob
import os
import unittest

from tests._load import ROOT

POSIX_MODS = {"fcntl", "pwd", "grp", "termios", "resource"}

# os.kill(<pid>, 0) is TerminateProcess on Windows — allowed only where a Windows branch precedes it.
KILL0_OK = {
    ("sidereus/config.py", "pid_alive"),         # IS_WIN uses OpenProcess first
    ("sidereus_cli.py", "pid_alive"),            # delegates to config.pid_alive; IS_WIN returns early
    ("hooks/mailbox_stop.py", "watch_alive"),  # os.name == "nt" returns False first
}
# POSIX path literals allowed by (file, function).
LITERAL_OK = {
    ("sidereus_cli.py", "build_plist"),          # launchd plist default python (macOS only)
    ("sidereus_cli.py", "setup_python"),         # documented macOS python, used only behind IS_MAC
    ("sidereus/demo_tools.py", "_demo_runtime"),  # demo display string, never opened
}


def _files():
    pats = ["chat_server.py", "sidereus/*.py", "sidereus_cli.py", "mailbox_*.py", "monitor_stream.py",
            "watch_bus.py", "readcheck.py", "hooks/*.py"]
    out = []
    for p in pats:
        out += sorted(glob.glob(os.path.join(ROOT, p)))
    return [os.path.relpath(f, ROOT).replace(os.sep, "/") for f in out]   # allow-list keys use `/` on every OS


def _parents(tree):
    par = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            par[c] = n
    return par


def _chain(node, par):
    while node in par:
        node = par[node]
        yield node


def _func(node, par):
    for a in _chain(node, par):
        if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return a.name
    return ""


def _src(node):
    try:
        return ast.unparse(node)        # 3.9+
    except Exception:
        return ""


def _is_os_attr(node, name):
    return (isinstance(node, ast.Attribute) and node.attr == name
            and isinstance(node.value, ast.Name) and node.value.id == "os")


class WinStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trees = {}
        for rel in _files():
            with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
                cls.trees[rel] = ast.parse(f.read(), rel)

    def test_files_found(self):
        self.assertIn("chat_server.py", self.trees)
        self.assertIn("sidereus_cli.py", self.trees)

    def test_no_module_level_posix_import(self):
        bad = []
        for rel, tree in self.trees.items():
            for n in tree.body:        # ⚠top-level only; a try/except ImportError guard is a nested node and passes
                names = []
                if isinstance(n, ast.Import):
                    names = [a.name.split(".")[0] for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module:
                    names = [n.module.split(".")[0]]
                for m in names:
                    if m in POSIX_MODS:
                        bad.append("%s:%d import %s" % (rel, n.lineno, m))
        self.assertEqual(bad, [], "module-level POSIX-only imports fail on Windows")

    def test_kill_zero_only_in_allow_list(self):
        bad = []
        for rel, tree in self.trees.items():
            par = _parents(tree)
            for n in ast.walk(tree):
                if (isinstance(n, ast.Call) and _is_os_attr(n.func, "kill") and len(n.args) == 2
                        and isinstance(n.args[1], ast.Constant) and n.args[1].value == 0
                        and (rel, _func(n, par)) not in KILL0_OK):
                    bad.append("%s:%d os.kill(pid, 0) in %s()" % (rel, n.lineno, _func(n, par) or "<module>"))
        self.assertEqual(bad, [], "os.kill(pid, 0) terminates the process on Windows")

    def test_getuid_guarded(self):
        bad = []
        for rel, tree in self.trees.items():
            par = _parents(tree)
            for n in ast.walk(tree):
                if not _is_os_attr(n, "getuid"):
                    continue
                ok = False
                for a in _chain(n, par):
                    if isinstance(a, ast.Try):
                        ok = True
                    elif isinstance(a, ast.If) and "IS_MAC" in _src(a.test):
                        ok = True
                    if ok:
                        break
                if not ok:
                    bad.append("%s:%d os.getuid outside try / IS_MAC" % (rel, n.lineno))
        self.assertEqual(bad, [], "os.getuid does not exist on Windows")

    def test_no_posix_path_literals(self):
        bad = []
        for rel, tree in self.trees.items():
            par = _parents(tree)
            for n in ast.walk(tree):
                if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
                    continue
                v = n.value
                if not (v == "/usr/bin/python3" or v == "/tmp" or v.startswith("/tmp/")):  # nosec B108 -- fake path, never touched
                    continue
                if (rel, _func(n, par)) in LITERAL_OK:
                    continue
                bad.append("%s:%d %r" % (rel, n.lineno, v))
        self.assertEqual(bad, [], "POSIX-only path literal (use sys.executable / tempfile)")

    def test_path_not_split_on_colon(self):
        bad = []
        for rel, tree in self.trees.items():
            for n in ast.walk(tree):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                    continue
                f = n.func
                hit = False
                # ":".join(<...PATH...>)
                if (f.attr == "join" and isinstance(f.value, ast.Constant) and f.value.value == ":"
                        and any("PATH" in _src(a) for a in n.args)):
                    hit = True
                # <...PATH...>.split(":")
                if (f.attr == "split" and n.args and isinstance(n.args[0], ast.Constant)
                        and n.args[0].value == ":" and "PATH" in _src(f.value)):
                    hit = True
                if hit:
                    bad.append("%s:%d %s" % (rel, n.lineno, _src(n)[:80]))
        self.assertEqual(bad, [], "PATH must use os.pathsep (':' splits C:\\ entries)")


if __name__ == "__main__":
    unittest.main()
