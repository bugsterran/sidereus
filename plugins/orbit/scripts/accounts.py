#!/usr/bin/env python3
"""Orbit: pick a Claude Code config folder (CLAUDE_CONFIG_DIR) per project folder.

Registry ~/.claude-accounts (plain text; comments and unknown lines survive every edit):
    account <name> <dir>     map <folder> <name>     default <name>
CLI: add · rename · map · unmap · default · remove · list · resolve · shell install|uninstall · hook-session-start.
Stdlib only, Python 3.9. HOME is read from the environment at call time (tests run with a tmp HOME).
⚠Never reads or copies credentials: sign-in status is only `"oauthAccount" in <.claude.json>`, values are never printed.
"""
import json
import os
import re
import shutil
import sys

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
RESERVED = ("accounts",)        # ~/.claude-accounts is the registry file itself
COPY_ITEMS = ("settings", "agents", "skills", "commands", "mcp")
# Never copied, even when found inside a copied folder.
NEVER = (".credentials.json", ".claude.json", "projects", "history.jsonl", "plugins")
# ⚠On-disk names keep the pre-rename "folder-accounts" spelling (rc markers, stable copy, .bak/.tmp suffixes,
# FA_* env vars, ~/.claude-accounts): existing installs are found, refreshed and uninstalled by these exact strings.
BEGIN = "# >>> folder-accounts >>>"
END = "# <<< folder-accounts <<<"
HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.join(os.path.dirname(HERE), "shell", "launcher.sh")


class UsageError(Exception):
    def __init__(self, msg, code=1):
        Exception.__init__(self, msg)
        self.code = code


def home():
    return os.environ.get("HOME") or os.path.expanduser("~")


def registry_path():
    return os.path.join(home(), ".claude-accounts")


def primary_dir():
    return os.path.join(home(), ".claude")


def stable_py():
    return os.path.join(home(), ".local", "share", "folder-accounts", "accounts.py")


def expand(p):
    p = p.strip()
    if p == "~" or p.startswith(("~/", "~" + os.sep)):
        p = home() + p[1:]
    return os.path.abspath(p)


def tilde(p):
    # The registry always stores "~/a/b" (one file shared by Git Bash and POSIX shells); "/" on every OS.
    h = os.path.abspath(home()).rstrip(os.sep)
    p = os.path.abspath(p)
    if os.path.normcase(p) == os.path.normcase(h):
        return "~"
    return "~/" + p[len(h) + 1:].replace(os.sep, "/") if under(p, h) else p


def real(p):
    return os.path.realpath(expand(p))


def under(child, parent):
    """True when `child` is `parent` or below it, on path-component boundaries (realpaths)."""
    c, q = os.path.normcase(child), os.path.normcase(parent)   # ⚠Windows paths compare case-insensitively
    return c == q or c.startswith(q.rstrip(os.sep) + os.sep)


# ---- registry -------------------------------------------------------------------------------------------------

def parse_line(line):
    """('account', name, dir) | ('map', folder, name) | ('default', name) | None for comments/unknown lines."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    parts = s.split()
    if parts[0] == "account" and len(parts) >= 3:
        return ("account", parts[1], s.split(None, 2)[2].strip())
    if parts[0] == "map" and len(parts) >= 3:
        body = s.split(None, 1)[1]
        folder, name = body.rsplit(None, 1)   # folder may contain spaces; the name never does
        return ("map", folder.strip(), name)
    if parts[0] == "default" and len(parts) == 2:
        return ("default", parts[1])
    return None


IGNORED = "not UTF-8, not owned by you, or writable by group/others"


def safe_owner(st):
    """Registry must be ours and not group/world-writable: it picks the config folder (hooks, settings) we run with."""
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        return False
    # ⚠Windows st_mode reports 0o666 for every writable file (ACLs are not mode bits): the check would refuse all.
    return os.name == "nt" or not st.st_mode & 0o022


class Registry(object):
    def __init__(self, lines, unreadable=False):
        self.lines = lines              # raw lines without trailing newline
        self.unreadable = unreadable

    @classmethod
    def load(cls):
        try:
            with open(registry_path(), encoding="utf-8") as f:
                if not safe_owner(os.fstat(f.fileno())):
                    return cls([], True)
                text = f.read()
        except (IOError, OSError):
            return cls([])
        except ValueError:              # not UTF-8: behave as empty (primary only), never rewrite it
            return cls([], True)
        return cls(text.split("\n")[:-1] if text.endswith("\n") else text.split("\n") if text else [])

    def save(self):
        if self.unreadable:
            raise UsageError("registry %s is ignored (%s); fix or remove it first" % (tilde(registry_path()), IGNORED))
        check_writer()
        new = not os.path.exists(registry_path())
        write_atomic(registry_path(), "".join(l + "\n" for l in self.lines), 0o600 if new else None)

    def entries(self, kind):
        return [(i, e) for i, e in ((i, parse_line(l)) for i, l in enumerate(self.lines)) if e and e[0] == kind]

    def accounts(self):
        """[(name, abs dir)] in file order; the primary ~/.claude is added as `default` when not registered."""
        out, seen = [], set()
        for _, e in self.entries("account"):
            # ⚠Hand edits: a bad label or a control char (tab) in the dir would corrupt the launcher's name<TAB>dir.
            if not NAME_RE.match(e[1]) or bad_chars(e[2]):
                continue
            if e[1] not in seen:
                seen.add(e[1])
                out.append((e[1], expand(e[2])))
        prim = os.path.realpath(primary_dir())
        if not any(os.path.realpath(d) == prim for _, d in out) and "default" not in seen:
            out.insert(0, ("default", primary_dir()))
        return out

    def live_accounts(self):
        # Only directories count as accounts.
        return [(n, d) for n, d in self.accounts() if os.path.isdir(d)]

    def maps(self):
        return [(expand(e[1]), e[2]) for _, e in self.entries("map")]

    def default(self):
        d = self.entries("default")
        return d[-1][1][1] if d else None

    def drop(self, pred):
        self.lines = [l for l in self.lines if not pred(parse_line(l))]


def write_atomic(path, text, mode=None):
    path = os.path.realpath(path)       # ⚠a symlinked rc (dotfile managers) keeps its link; the target is rewritten
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    tmp = path + ".tmp-folder-accounts"
    if os.path.isfile(tmp) and not os.path.islink(tmp):
        os.remove(tmp)                  # leftover of a killed run; a symlink is not removed and the open refuses it
    # ⚠O_EXCL + O_NOFOLLOW: a pre-planted tmp (file or symlink) is refused instead of written through,
    # and the file is 0600 from creation, so secrets never sit under umask perms before the chmod.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        elif os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def check_name(name):
    if not NAME_RE.match(name or "") or name in RESERVED:
        raise UsageError("invalid account name %r (a-z 0-9 _ -, max 32, not %s)" % (name, "/".join(RESERVED)))


def find(reg, name):
    for n, d in reg.accounts():
        if n == name:
            return d
    return None


# ---- resolve --------------------------------------------------------------------------------------------------

def mapped(reg, cwd):
    """Nearest mapped account name for cwd (longest matching folder), or None."""
    rc = os.path.realpath(cwd)
    names = dict(reg.live_accounts())
    best = None
    for folder, name in reg.maps():
        f = os.path.realpath(folder)
        if name in names and under(rc, f) and (best is None or len(f) > len(best[0])):
            best = (f, name)
    return best[1] if best else None


def out_dir(d):
    return "-" if os.path.realpath(d) == os.path.realpath(primary_dir()) else os.path.abspath(d)


def resolve(cwd, account=None, tty=False, ask_in=None, ask_out=None):
    """(name, dir or '-'). Order: --account > nearest map > default > single account > prompt (tty) > primary."""
    reg = Registry.load()
    live = reg.live_accounts()
    names = dict(live)
    if account:
        if account not in names:
            raise UsageError("unknown account %r; known: %s" % (account, ", ".join(n for n, _ in live) or "none"), 2)
        return account, out_dir(names[account])
    name = mapped(reg, cwd)
    if not name and reg.default() in names:
        name = reg.default()
    if not name and len(live) == 1:
        name = live[0][0]
    if not name and len(live) >= 2 and tty:
        name = prompt(reg, live, cwd, ask_in, ask_out)
    if not name:
        prim = os.path.realpath(primary_dir())
        name = next((n for n, d in live if os.path.realpath(d) == prim), live[0][0] if live else "default")
        return name, out_dir(names.get(name, primary_dir()))
    return name, out_dir(names[name])


def prompt(reg, live, cwd, ask_in, ask_out):
    own = ask_in is None
    if own:
        try:
            ask_in = open("/dev/tty", encoding="utf-8")
            ask_out = open("/dev/tty", "w", encoding="utf-8")
        except (IOError, OSError):
            return None
    try:
        ask_out.write("Claude account for %s:\n" % tilde(cwd))
        for i, (n, d) in enumerate(live, 1):
            ask_out.write("  %d) %s  %s\n" % (i, n, tilde(d)))
        name = None
        for _ in range(3):
            ask_out.write("number [1]: ")
            ask_out.flush()
            ans = ask_in.readline()
            if not ans:
                return None
            ans = ans.strip() or "1"
            if ans.isdigit() and 1 <= int(ans) <= len(live):
                name = live[int(ans) - 1][0]
                break
        if not name:
            return None
        ask_out.write("remember for this folder? (Y/n): ")
        ask_out.flush()
        ans = ask_in.readline()
        # Enter remembers; EOF (no answer at all) does not.
        if ans and ans.strip().lower() in ("", "y", "yes"):
            try:
                set_map(reg, cwd, name)
                reg.save()
            except UsageError as e:     # still start with the chosen account, just not remembered
                sys.stderr.write("orbit: not remembered: %s\n" % e)
        return name
    finally:
        if own:
            ask_in.close()
            ask_out.close()


# ---- registry commands ----------------------------------------------------------------------------------------

def bad_chars(p):
    return any(ord(c) < 32 or ord(c) == 127 for c in p)


def check_path(p):
    # ⚠A newline in a path would write extra registry lines.
    if bad_chars(p):
        raise UsageError("refusing a path with control characters: %r" % p)


def check_writer():
    """Refuse writes when HOME belongs to another user (e.g. sudo keeping HOME): files would end up root-owned."""
    if hasattr(os, "geteuid") and os.stat(home()).st_uid != os.geteuid():
        raise UsageError("HOME %s is not owned by the current user (sudo?); run without sudo" % home())


def set_map(reg, folder, name):
    check_path(folder)
    rf = real(folder)
    reg.drop(lambda e: e is not None and e[0] == "map" and real(e[1]) == rf)
    reg.lines.append("map %s %s" % (tilde(os.path.abspath(expand(folder))), name))


def ensure_primary_line(reg):
    prim = os.path.realpath(primary_dir())
    acc = [e for _, e in reg.entries("account")]
    if not any(real(e[2]) == prim for e in acc) and not any(e[1] == "default" for e in acc):
        reg.lines.append("account default ~/.claude")


def mcp_source(src_dir):
    if os.path.realpath(src_dir) == os.path.realpath(primary_dir()):
        return os.path.join(home(), ".claude.json")
    return os.path.join(src_dir, ".claude.json")


def copy_plan(src, dst, items):
    """[(label, src path, dst path, note)] — note 'skip: exists' when the target is already there."""
    plan = []
    for it in items:
        if it == "settings":
            s, t = os.path.join(src, "settings.json"), os.path.join(dst, "settings.json")
        elif it == "mcp":
            s, t = mcp_source(src), os.path.join(dst, ".claude.json")
        else:
            s, t = os.path.join(src, it), os.path.join(dst, it)
        if it != "mcp" and os.path.islink(s):
            note = "skip: exists" if os.path.lexists(t) else "link"     # recreated, never followed
        elif not os.path.exists(s):
            note = "skip: not in source"
        elif os.path.exists(t) and it != "mcp" and not os.path.isdir(t):
            note = "skip: exists"
        elif it == "mcp" and os.path.exists(t):
            note = "skip: exists"
        else:
            note = "copy"
        plan.append((it, s, t, note))
    return plan


def copy_tree(s, t):
    # Never overwrite: only entries missing in the target are copied; credential/session names are skipped.
    if not os.path.isdir(t):
        os.makedirs(t)
    for n in sorted(os.listdir(s)):
        if n in NEVER:
            continue
        a, b = os.path.join(s, n), os.path.join(t, n)
        if os.path.islink(a):
            if not os.path.lexists(b):
                os.symlink(os.readlink(a), b)
        elif os.path.isdir(a):
            copy_tree(a, b)
        elif not os.path.lexists(b):
            shutil.copy2(a, b)


def do_copy(plan):
    for it, s, t, note in plan:
        if note == "link":
            os.symlink(os.readlink(s), t)
            continue
        if note != "copy":
            continue
        if it == "mcp":
            try:
                with open(s, encoding="utf-8") as f:
                    servers = json.load(f).get("mcpServers")
            except (IOError, OSError, ValueError, AttributeError):
                servers = None
            if isinstance(servers, dict):
                write_atomic(t, json.dumps({"mcpServers": servers}, indent=2) + "\n", 0o600)
        elif it == "settings":
            # settings.json `env` / `apiKeyHelper` may hold tokens, so the copy is 0600 like the mcp one.
            with open(s, encoding="utf-8", newline="") as f:
                write_atomic(t, f.read(), 0o600)
        elif os.path.isdir(s):
            copy_tree(s, t)
        else:
            shutil.copy2(s, t)


def check_dir(reg, name, d):
    """Refuse /, the home dir or above, and a folder already registered under another name."""
    rd, hp = os.path.realpath(d), os.path.realpath(home())
    # A root at / or at/above home would contain every project folder and the other account folders.
    if rd == os.path.dirname(rd) or under(hp, rd):
        raise UsageError("refusing %s as an account folder" % tilde(d))
    for n, x in reg.accounts():
        if n != name and os.path.realpath(x) == rd:
            raise UsageError("%s is already registered as %r (use rename)" % (tilde(d), n))


def cmd_add(args, out):
    name, items, yes, dirarg, shell, rc = None, [], False, None, False, None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--yes":
            yes = True
        elif a == "--shell":
            shell = True
        elif a == "--rc" and i + 1 < len(args):
            rc = args[i + 1]
            i += 1
        elif a == "--dir" and i + 1 < len(args):
            dirarg = args[i + 1]
            i += 1
        elif a.startswith("--dir="):
            dirarg = a.split("=", 1)[1]
        elif a == "--copy" and i + 1 < len(args):
            items = [x.strip() for x in args[i + 1].split(",") if x.strip()]
            i += 1
        elif a.startswith("--copy="):
            items = [x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()]
        elif name is None and not a.startswith("-"):
            name = a
        else:
            raise UsageError("usage: add <name> [--dir PATH] [--copy settings,agents,skills,commands,mcp] [--rc FILE] [--shell] [--yes]")
        i += 1
    check_name(name)
    bad = [x for x in items if x not in COPY_ITEMS]
    if bad:
        raise UsageError("unknown --copy item(s): %s (allowed: %s)" % (", ".join(bad), ",".join(COPY_ITEMS)))
    reg = Registry.load()
    # The name is only a label: --dir registers any folder under it (rename later without moving the folder).
    dst = expand(dirarg) if dirarg and dirarg.strip() else os.path.join(home(), ".claude-" + name)
    have = find(reg, name)
    if have and os.path.realpath(have) != os.path.realpath(dst):
        raise UsageError("account %r already registered for %s" % (name, tilde(have)))
    check_path(dst)
    check_dir(reg, name, dst)
    plan = copy_plan(primary_dir(), dst, items)
    rc = expand(rc) if rc else default_rc()
    check_path(rc)
    # The launcher block comes with the first add: install plugin, add, run `claude`.
    need_shell = shell or not shell_ready(rc)
    if not yes:
        out.write("dry run (nothing written; add --yes to apply):\n")
        out.write("  folder  %s%s\n" % (tilde(dst), "  (exists, contents kept)" if os.path.isdir(dst) else "  (new)"))
        for it, s, t, note in plan:
            out.write("  %-8s %s -> %s  [%s]\n" % (it, tilde(s), tilde(t), note))
            if it == "mcp" and note == "copy":
                out.write("           mcpServers only, including their env values (may hold tokens); file mode 0600\n")
            if it == "settings" and note == "copy":
                out.write("           as is, including env and apiKeyHelper (may hold tokens); file mode 0600\n")
        if need_shell:
            out.write("  shell   %s: %s block in %s (backup %s.bak-folder-accounts once),\n"
                      "          copy accounts.py -> %s\n" % ("reinstall" if shell else "launcher not installed",
                                                             "replace" if find_block(read_rc(rc)[0]) else "append",
                                                             tilde(rc), tilde(rc), tilde(stable_py())))
        return 0
    existed = os.path.isdir(dst)
    if not existed:
        os.makedirs(dst, 0o700)
        # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions -- owner-only dir, x is needed
        os.chmod(dst, 0o700)
    do_copy(plan)
    if not have:
        ensure_primary_line(reg)
        reg.lines.append("account %s %s" % (name, tilde(dst)))
        reg.save()
    out.write("%s %s -> %s%s\n" % ("registered" if not have else "already registered", name, tilde(dst),
                                   " (existing folder, contents kept)" if existed else ""))
    out.write("plugins must be installed per account\n")
    out.write("sign in: claude -A %s, then /login\n" % name)
    if need_shell:
        old, exists = read_rc(rc)
        shell_apply("install", rc, old, exists, rc_install(old))
        out.write("launcher installed in %s; open a new shell\n" % tilde(rc))
    return 0


def cmd_rename(args, out):
    if len(args) != 2:
        raise UsageError("usage: rename <old> <new>")
    old, new = args
    check_name(new)
    reg = Registry.load()
    if not find(reg, old):
        raise UsageError("unknown account %r" % old, 2)
    if find(reg, new):
        raise UsageError("account %r already exists" % new)
    if not any(e[1] == old for _, e in reg.entries("account")):
        ensure_primary_line(reg)    # the implicit primary "default" gets its line first
    # Label only: the account line, maps and default change; the folder is untouched.
    for i, l in enumerate(reg.lines):
        e = parse_line(l)
        if not e:
            continue
        if e[0] == "account" and e[1] == old:
            reg.lines[i] = "account %s %s" % (new, e[2])
        elif e[0] == "map" and e[2] == old:
            reg.lines[i] = "map %s %s" % (e[1], new)
        elif e[0] == "default" and e[1] == old:
            reg.lines[i] = "default " + new
    reg.save()
    out.write("renamed %s -> %s (folder kept: %s)\n" % (old, new, tilde(find(reg, new))))
    return 0


def cmd_map(args, out):
    if len(args) == 1:
        folder, name = os.getcwd(), args[0]
    elif len(args) == 2:
        folder, name = args
    else:
        raise UsageError("usage: map [folder] <name>")
    reg = Registry.load()
    if not find(reg, name):
        raise UsageError("unknown account %r" % name, 2)
    if not os.path.isdir(expand(folder)):
        raise UsageError("not a folder: %s" % folder)
    set_map(reg, folder, name)
    reg.save()
    out.write("map %s -> %s\n" % (tilde(expand(folder)), name))
    return 0


def cmd_unmap(args, out):
    if len(args) > 1:
        raise UsageError("usage: unmap [folder]")
    folder = args[0] if args else os.getcwd()
    reg = Registry.load()
    rf = real(folder)
    n = len(reg.lines)
    reg.drop(lambda e: e is not None and e[0] == "map" and real(e[1]) == rf)
    if len(reg.lines) == n:
        out.write("no map for %s\n" % tilde(expand(folder)))
        return 0
    reg.save()
    out.write("unmapped %s\n" % tilde(expand(folder)))
    return 0


def cmd_default(args, out):
    if len(args) != 1:
        raise UsageError("usage: default <name>")
    reg = Registry.load()
    if not find(reg, args[0]):
        raise UsageError("unknown account %r" % args[0], 2)
    reg.drop(lambda e: e is not None and e[0] == "default")
    reg.lines.append("default " + args[0])
    reg.save()
    out.write("default -> %s\n" % args[0])
    return 0


def cmd_remove(args, out):
    if len(args) != 1:
        raise UsageError("usage: remove <name>")
    name = args[0]
    reg = Registry.load()
    if not any(e[1] == name for _, e in reg.entries("account")):
        raise UsageError("account %r is not registered" % name, 2)
    d = find(reg, name)
    reg.drop(lambda e: e is not None and ((e[0] == "account" and e[1] == name) or (e[0] == "map" and e[2] == name)
                                          or (e[0] == "default" and e[1] == name)))
    reg.save()
    out.write("unregistered %s (folder kept: %s)\n" % (name, tilde(d)))
    return 0


OAUTH_KEY = re.compile(rb'"oauthAccount"\s*:')
SCAN_CHUNK = 1 << 20
SCAN_CAP = 64 << 20


def signed_in(d):
    """True/False/None: byte scan for the "oauthAccount" key; never parsed, so no value is decoded. None = unknown."""
    try:
        with open(mcp_source(d), "rb") as f:
            tail, total = b"", 0
            while total < SCAN_CAP:
                chunk = f.read(SCAN_CHUNK)
                if not chunk:
                    return False
                total += len(chunk)
                buf = tail + chunk
                if OAUTH_KEY.search(buf):
                    return True
                tail = buf[-64:]        # a key split across two chunks
            return None
    except (IOError, OSError) as e:
        return False if getattr(e, "errno", None) == 2 else None


def cmd_list(args, out):
    reg = Registry.load()
    if reg.unreadable:
        out.write("registry %s is ignored (%s); showing the primary folder only\n" % (tilde(registry_path()), IGNORED))
    dflt = reg.default()
    maps = reg.maps()
    known = set()
    for n, d in reg.accounts():
        known.add(os.path.realpath(d))
        if not os.path.isdir(d):
            state = "missing folder"
        else:
            s = signed_in(d)
            state = "signed in" if s else "not signed in" if s is False else "sign-in unknown"
        out.write("%s%s  %s  [%s]\n" % ("* " if n == dflt else "  ", n, tilde(d), state))
        for folder, mn in maps:
            if mn == n:
                out.write("      map %s\n" % tilde(folder))
    h = home()
    try:
        extra = sorted(x for x in os.listdir(h) if x.startswith(".claude-"))
    except OSError:
        extra = []
    for x in extra:
        p = os.path.join(h, x)
        if not os.path.isdir(p) or os.path.realpath(p) in known:
            continue
        if not NAME_RE.match(x[len(".claude-"):]):
            continue
        if os.path.isdir(os.path.join(p, "projects")) or os.path.isfile(os.path.join(p, ".claude.json")):
            out.write("  found %s  (not registered; orbit add %s)\n" % (tilde(p), x[len(".claude-"):]))
    return 0


def cmd_resolve(args, out, ask_in=None, ask_out=None):
    cwd, account, tty = os.getcwd(), None, False
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--cwd", "--account", "--tty") and i + 1 < len(args):
            v = args[i + 1]
            if a == "--cwd":
                cwd = v
            elif a == "--account":
                account = v
            else:
                tty = v == "1"
            i += 2
        else:
            raise UsageError("usage: resolve --cwd P [--account N] --tty 0|1")
    name, d = resolve(cwd, account, tty, ask_in, ask_out)
    # ⚠Third field only when the launcher asks via env: an older launcher would read "dir\t1" as the dir.
    if os.environ.get("FA_RESOLVE_FIELDS") == "3":
        out.write("%s\t%s\t%d\n" % (name, d, 0 if signed_in(primary_dir() if d == "-" else d) is False else 1))   # unknown: no hint
    else:
        out.write("%s\t%s\n" % (name, d))
    return 0


# ---- rc editor ------------------------------------------------------------------------------------------------

def default_rc():
    sh = os.path.basename(os.environ.get("SHELL", ""))
    return os.path.join(home(), ".bashrc" if sh == "bash" else ".zshrc")


def block_text():
    with open(LAUNCHER, encoding="utf-8") as f:
        body = f.read()
    if not body.endswith("\n"):
        body += "\n"
    return "%s\nexport FA_PY=\"$HOME/.local/share/folder-accounts/accounts.py\"\n%s%s\n" % (BEGIN, body, END)


def find_block(text):
    """(start, end) offsets of the block (end after END's newline), or None."""
    s = text.find(BEGIN + "\n")
    while s > 0 and text[s - 1] != "\n":
        s = text.find(BEGIN + "\n", s + 1)
    if s < 0:
        return None
    e = text.find("\n" + END, s)
    if e < 0:
        return None
    e += len("\n" + END)
    if e < len(text) and text[e] == "\n":
        e += 1
    return s, e


def rc_install(text):
    blk = block_text()
    at = find_block(text)
    if at:
        return text[:at[0]] + blk + text[at[1]:]
    # Appended as "\n" + block; uninstall drops that one separator again, so the round trip is byte-identical.
    return text + ("\n" + blk if text else blk)


def rc_uninstall(text):
    at = find_block(text)
    if not at:
        return text
    s, e = at
    if e >= len(text) and s > 0 and text[s - 1] == "\n":
        s -= 1      # block at EOF: also remove the separator install added
    return text[:s] + text[e:]


def cmd_shell(args, out):
    if not args or args[0] not in ("install", "uninstall"):
        raise UsageError("usage: shell install|uninstall [--rc FILE] [--yes]")
    act, rest = args[0], args[1:]
    rc, yes = None, False
    i = 0
    while i < len(rest):
        if rest[i] == "--rc" and i + 1 < len(rest):
            rc = rest[i + 1]
            i += 2
        elif rest[i] == "--yes":
            yes = True
            i += 1
        else:
            raise UsageError("usage: shell install|uninstall [--rc FILE] [--yes]")
    rc = expand(rc) if rc else default_rc()
    old, exists = read_rc(rc)
    new = rc_install(old) if act == "install" else rc_uninstall(old)
    if not yes:
        out.write("dry run (nothing written; add --yes to apply):\n")
        if act == "install":
            out.write("  %s block in %s\n" % ("replace" if find_block(old) else "append", tilde(rc)))
            out.write("  copy %s -> %s\n" % (tilde(os.path.abspath(__file__)), tilde(stable_py())))
            out.write(block_text())
        else:
            out.write("  %s\n" % (("remove block from " + tilde(rc)) if new != old else "no block in " + tilde(rc)))
        return 0
    shell_apply(act, rc, old, exists, new)
    out.write("%s %s; open a new shell\n" % ("installed in" if act == "install" else "removed from", tilde(rc)))
    return 0


def read_rc(rc):
    try:
        with open(rc, encoding="utf-8", newline="") as f:
            return f.read(), True
    except (IOError, OSError):
        return "", False


def shell_ready(rc):
    """True when the rc has the block and the stable accounts.py copy exists."""
    return bool(find_block(read_rc(rc)[0])) and os.path.isfile(stable_py())


def shell_apply(act, rc, old, exists, new):
    if act == "install":
        dst = stable_py()
        if not os.path.isdir(os.path.dirname(dst)):
            os.makedirs(os.path.dirname(dst))
        if os.path.realpath(dst) != os.path.realpath(__file__):
            shutil.copyfile(os.path.abspath(__file__), dst)
    if new != old:
        bak = rc + ".bak-folder-accounts"
        if exists and not os.path.lexists(bak):     # ⚠lexists: a dangling symlink must not be written through
            shutil.copy2(rc, bak)
        write_atomic(rc, new, None if exists else 0o644)


# ---- SessionStart hook ----------------------------------------------------------------------------------------

def hook_session_start(stdin, out):
    try:
        data = json.loads(stdin.read() or "{}")
        cwd = data.get("cwd") if isinstance(data, dict) else None
        if not cwd:
            return 0
        reg = Registry.load()
        name = mapped(reg, cwd)
        if not name:
            return 0
        want = dict(reg.live_accounts())[name]
        run = os.environ.get("CLAUDE_CONFIG_DIR") or primary_dir()
        if os.path.realpath(expand(run)) == os.path.realpath(want):
            return 0
        rr = os.path.realpath(expand(run))
        cur = next((n for n, d in reg.accounts() if os.path.realpath(d) == rr), tilde(expand(run)))
        msg = ("This folder is mapped to account %s; this session runs as %s "
               "(start with `claude` from a new shell)." % (name, cur))
        out.write(json.dumps({"systemMessage": msg, "hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": msg}}) + "\n")
    except Exception:       # a hook never blocks or breaks session start
        pass
    return 0


# ---- main -----------------------------------------------------------------------------------------------------

USAGE = """usage: orbit <command>
  add <name> [--dir PATH] [--copy settings,agents,skills,commands,mcp] [--rc FILE] [--shell] [--yes]
  rename <old> <new>
  map [folder] <name> | unmap [folder] | default <name> | remove <name> | list
  resolve --cwd P [--account N] --tty 0|1
  shell install|uninstall [--rc FILE] [--yes]
  hook-session-start
"""

CMDS = {"add": cmd_add, "rename": cmd_rename, "map": cmd_map, "unmap": cmd_unmap, "default": cmd_default, "remove": cmd_remove,
        "list": cmd_list, "resolve": cmd_resolve, "shell": cmd_shell}


def main(argv, stdin=None, out=None, err=None):
    stdin, out, err = stdin or sys.stdin, out or sys.stdout, err or sys.stderr
    if not argv or argv[0] in ("-h", "--help", "help"):
        out.write(USAGE)
        return 0
    if argv[0] == "hook-session-start":
        return hook_session_start(stdin, out)
    fn = CMDS.get(argv[0])
    if not fn:
        err.write(USAGE)
        return 2
    try:
        if argv[0] not in ("list", "resolve"):
            check_writer()
        return fn(argv[1:], out)
    except UsageError as e:
        err.write("orbit: %s\n" % e)
        return e.code
    except (IOError, OSError) as e:
        err.write("orbit: %s\n" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
