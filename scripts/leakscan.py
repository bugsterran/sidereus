#!/usr/bin/python3
"""Leak scan over shipped files: personal/company identifiers, real-looking session UUIDs, secrets.

Shipped = `git ls-files` minus what .distignore excludes (git does the gitignore matching).
Exit 1 and print file:line on any hit. A line containing `leakscan: allow` is skipped.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sidereus import redact as _r  # noqa: E402  (secret regexes shared with the work popup)

ALLOW_MARK = "leakscan: allow"
# Fabricated ids and fake secrets are expected here (fixtures, demo data); identifiers are still scanned.
FIXTURE_PREFIXES = ("tests/", "sidereus/demo_data.py")
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
# /Users/<seg>: generic placeholder segments are fine, a real login is not.  leakscan: allow
HOMEDIR = re.compile(r"/Users/([^/\s\"'`)]*)")  # leakscan: allow
HOME_PLACEHOLDERS = {"", "x", "a", "me", "you", "user", "username", "name", "demo", "example", "alice", "bob",
                     "<user>", "<you>", "$user", "${user}", "..."}
# Named secrets: only a long opaque literal counts (code like `token = get()` must not fire).
_OPAQUE = re.compile(r"^[\"']?[A-Za-z0-9+/_\-]{24,}={0,2}[\"']?$")
# ⚠Boundary added: bare _TOKENS matches the "sk-" inside "task-notification".
SECRETS = (("private-key", _r._PEM), ("token", re.compile(r"(?<![A-Za-z0-9])" + _r._TOKENS.pattern)),
           ("jwt", _r._JWT))


def identifiers(name, email, login=None):
    """Case-insensitive identifier regexes from git user.name/user.email (+ login name)."""
    words = set()
    if name:
        words.add(name.strip())
        words.update(p.strip() for p in name.split("/") if len(p.strip()) >= 3)
    if email and "@" in email:
        local, dom = email.split("@", 1)
        if len(local) >= 3:
            words.add(local)
        head = dom.split(".")[0]
        if len(head) >= 3:
            words.add(head)
    if login and len(login) >= 3:
        words.add(login)
    return [re.compile(r"(?i)(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])") for w in sorted(words) if w]


def scan_text(rel, text, idents):
    """Return [(rel, lineno, kind, snippet)] for one file's text."""
    hits = []
    fixture = rel.startswith(FIXTURE_PREFIXES)
    for n, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARK in line:
            continue
        for rx in idents:
            m = rx.search(line)
            if m:
                hits.append((rel, n, "ident", m.group(0)))
        for m in HOMEDIR.finditer(line):
            if m.group(1).lower() not in HOME_PLACEHOLDERS:
                hits.append((rel, n, "homedir", m.group(0)))
        if fixture:
            continue
        m = UUID.search(line)
        if m:
            hits.append((rel, n, "uuid", m.group(0)))
        for kind, rx in SECRETS:
            m = rx.search(line)
            if m:
                hits.append((rel, n, kind, m.group(0)[:24]))
        for rx, g in ((_r._ENVKV, 2), (_r._JSONKV, 2)):
            for m in rx.finditer(line):
                if _OPAQUE.match(m.group(g)) and re.search(r"\d", m.group(g)) and re.search(r"[A-Za-z]", m.group(g)):
                    hits.append((rel, n, "named-secret", m.group(1)[:24]))
    return hits


def scan_file(root, rel, idents):
    try:
        with open(os.path.join(root, rel), "rb") as f:
            raw = f.read()
    except OSError:
        return []
    if b"\0" in raw[:8192]:
        return []   # binary
    return scan_text(rel, raw.decode("utf-8", "replace"), idents)


def _git(root, *args):
    return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, check=True).stdout


def shipped(root):
    tracked = [p for p in _git(root, "ls-files", "-z").split("\0") if p]
    excl = os.path.join(root, ".distignore")
    if not os.path.exists(excl):
        return tracked
    out = set(p for p in _git(root, "ls-files", "-z", "-i", "-c", "--exclude-from=" + excl).split("\0") if p)
    return [p for p in tracked if p not in out and os.path.isfile(os.path.join(root, p))]


def git_idents(root):
    # The global identity is the private one; a repo-local user.name/email that differs is the public
    # author name the repo ships under (LICENSE, plugin manifest), so its words are not leaks.
    def cfg(*k):
        try:
            return _git(root, "config", *k).strip()
        except subprocess.CalledProcessError:
            return ""
    gname, gmail = cfg("--global", "user.name"), cfg("--global", "user.email")
    lname, lmail = cfg("--local", "user.name"), cfg("--local", "user.email")
    priv = identifiers(gname or cfg("user.name"), gmail or cfg("user.email"), os.environ.get("USER"))
    # ⚠Only a local identity that differs from a present global one counts as public; with no global
    #   identity, or the same one set locally, nothing is subtracted (else the gate scans nothing).
    pub = set()
    if (gname or gmail) and (lname, lmail) != (gname, gmail):
        keep = {rx.pattern for rx in identifiers(gname, gmail)}
        pub = {rx.pattern for rx in identifiers(lname, lmail)} - keep
    return [rx for rx in priv if rx.pattern not in pub] + private_words(root)


def private_words(root):
    """Word regexes from tests/.private-deny (gitignored: one private project/company word per line, # = comment)."""
    p = os.path.join(root, "tests", ".private-deny")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        ws = [w.strip() for w in f.read().splitlines() if w.strip() and not w.startswith("#")]
    return [re.compile(r"(?i)(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])") for w in ws]


def main(root=ROOT):
    idents = git_idents(root)
    files = shipped(root)
    hits = []
    for rel in files:
        hits.extend(scan_file(root, rel, idents))
    for rel, n, kind, snip in hits:
        print("%s:%d: [%s] %s" % (rel, n, kind, snip))
    print("leakscan: %d shipped files, %d hits" % (len(files), len(hits)))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ROOT))
