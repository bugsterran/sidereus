#!/usr/bin/python3
"""Pipeline result-layer report: DATA_DIR/eval/<key>/reports/YYYY-MM-DD.md (core: sidereus/pl_outcome.py).

usage: pl_report.py --repo R --pipeline P.json [--auto] [--data-dir D]
  Writes the panel's fact sentences (pl_outcome.sentences) plus the PASSes that broke or had a fix follow
  (short sha, file names). ⚠Metadata only: no diffs, messages or file contents. Mode 0600, atomic replace.
  --auto      (pl_flow hook at run end, detached): exit 0 without writing while the newest report is under 7 days old.
  --data-dir  data folder to use instead of MAILBOX_DIR (the hook passes its own, so tests stay in their temp dir).
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_AGE_DAYS = 7
_NAME = re.compile(r"[a-z0-9-]{1,40}")
_now = time.time   # tests patch this


def _args(argv):
    ap = argparse.ArgumentParser(prog="pl_report.py")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pipeline", required=True)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--data-dir", default="")
    return ap.parse_args(argv)


def _load(data_dir):
    """Import the core after MAILBOX_DIR is set: config derives DATA_DIR (and every eval/evidence path) at import."""
    if data_dir:
        os.environ["MAILBOX_DIR"] = data_dir
    up = os.path.dirname(_HERE)
    if not os.path.isdir(os.path.join(up, "sidereus")):   # pipx/uv: sidereus/_bundle/scripts -> site-packages
        up = os.path.dirname(os.path.dirname(up))
    sys.path.insert(0, up)
    from sidereus import pl_outcome, pl_eval_view
    return pl_outcome, pl_eval_view


def _gate(P, name, repo, now):
    """{n, m} graded gates, or None when the eval core is absent or fails."""
    try:
        from sidereus import pl_eval
        g = pl_eval.graded_summary(dict(P, name=name), repo, now)
        return {"n": g.get("n"), "m": g.get("m")} if isinstance(g, dict) else None
    except Exception:
        return None


def render(name, date, sents, oc):
    """Markdown text of one report (pure; tests compare its sentences with pl_outcome.sentences)."""
    lines = ["# Pipeline report: %s" % name, "", "Date: %s" % date, ""]
    lines += ["- %s" % s for s in sents]
    rows = [x for x in ((oc or {}).get("result") or {}).get("list") or [] if x.get("broke") or x.get("fixed")]
    lines += ["", "## Passes that broke or had a fix follow", ""]
    if rows:
        lines += ["| commit | broke | fix followed | files |", "|---|---|---|---|"]
        for x in rows:
            fs = ", ".join("`%s`" % f.replace("`", "").replace("|", "/") for f in x.get("files") or [])
            lines.append("| %s | %s | %s | %s |" % (x.get("sha", ""), "yes" if x.get("broke") else "no",
                                                   "yes" if x.get("fixed") else "no", fs))
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def _write(path, text):
    d = os.path.dirname(path)
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".report-", suffix=".tmp")
    try:
        if hasattr(os, "fchmod"):   # mkstemp already creates 0600; this keeps it under any umask
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv=None):
    a = _args(sys.argv[1:] if argv is None else argv)
    if a.data_dir and not (os.path.isabs(a.data_dir) and os.path.isdir(a.data_dir)):
        print("pl_report: --data-dir must be an existing absolute folder", file=sys.stderr)
        return 2
    repo = os.path.realpath(a.repo)
    pf = os.path.realpath(a.pipeline)
    name = os.path.basename(pf)[:-5] if pf.endswith(".json") else ""
    if not os.path.isdir(repo) or not _NAME.fullmatch(name) or os.path.dirname(pf) != os.path.join(repo, ".claude", "pipelines"):
        print("pl_report: --pipeline must be <repo>/.claude/pipelines/<name>.json", file=sys.stderr)
        return 2
    OC, V = _load(a.data_dir)
    now = _now()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    if a.auto:
        last = OC.latest_report(repo)
        if last:
            age = (time.mktime(time.strptime(today, "%Y-%m-%d")) - time.mktime(time.strptime(last["date"], "%Y-%m-%d"))) / 86400
            if age < REPORT_AGE_DAYS:
                return 0
    try:
        with open(pf, encoding="utf-8") as f:
            P = json.load(f)
    except (OSError, ValueError):
        print("pl_report: unreadable pipeline", file=sys.stderr)
        return 2
    stages = [s for s in (P.get("stages") if isinstance(P, dict) else None) or [] if isinstance(s, dict)]
    oc = OC.outcome(repo, name, V.review_titles(stages), now)
    text = render(name, today, OC.sentences(_gate(P, name, repo, now), oc), oc)
    path = os.path.join(OC.OC_EVAL_DIR, OC.repo_key(repo), "reports", today + ".md")
    _write(path, text)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
