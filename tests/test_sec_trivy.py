"""sidereus/sec_trivy.py: plans, refs, parsers (fixture JSON in trivy `--format json` shape), fail reasons, merge, and
one runner run with trivy stubbed (no live tool, clock or network)."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus, ROOT

ST = sidereus("sec_trivy")
SC = sidereus("sec_checks")
AC = sidereus("arch_checks")
AV = sidereus("arch_verify")
SR = sidereus("sec_report")
LEAK = ("PLANTED-MESSAGE", "PLANTED-DESCRIPTION", "PLANTED-CODE", "9.9.9-installed")

CONFIG = {"SchemaVersion": 2, "ArtifactName": ".", "Results": [{"Target": "Dockerfile", "Class": "config", "Misconfigurations": [
    {"ID": "DS002", "AVDID": "AVD-DS-0002", "Title": "Image user should not be root", "Severity": "HIGH",
     "PrimaryURL": "https://avd.aquasec.com/misconfig/ds002", "Message": LEAK[0],
     "CauseMetadata": {"StartLine": 3, "Code": {"Lines": [{"Content": LEAK[2]}]}}}]}]}


def image(*vs):
    return {"SchemaVersion": 2, "ArtifactName": "x", "Results": [{"Target": "x (debian 12)", "Vulnerabilities": [
        dict({"PkgName": p, "Severity": s, "Description": LEAK[1], "InstalledVersion": LEAK[3], "Title": "t",
              "PrimaryURL": "https://avd.aquasec.com/nvd/" + c.lower(), "VulnerabilityID": c}, **({"FixedVersion": "2"} if fx else {}))
        for c, p, s, fx in vs]}]}


class Tmp(unittest.TestCase):
    def setUp(self):
        self.repo = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-trivy-"))
        self.addCleanup(shutil.rmtree, self.repo, True)

    def w(self, rel, text):
        fp = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)


class Detect(Tmp):
    def test_no_docker_files_no_rows(self):
        self.w("a.py", "x = 1\n")
        self.assertEqual(ST.detect(self.repo, lambda n: "/bin/" + n, True, True), [])

    def test_missing_says_install(self):   # R1
        self.w("Dockerfile", "FROM alpine:3.19\n")
        ps = ST.detect(self.repo, lambda n: None, True, True)
        self.assertEqual([(p["id"], p["status"]) for p in ps], [("trivy-config", "missing"), ("trivy-image", "missing")])
        self.assertTrue(all(p["why"].startswith("install:") and len(p["why"]) <= AC.WHY_MAX for p in ps))

    def test_config_argv_and_images_skipped(self):   # R1 R3
        self.w("Dockerfile", "FROM alpine:3.19\n")
        ps = ST.detect(self.repo, lambda n: "/bin/" + n, True, False)
        self.assertEqual(ps[0]["argv"], ["/bin/trivy", "config", "--misconfig-scanners", "dockerfile", "--format", "json",
                                         "--quiet", "."])
        self.assertEqual((ps[1]["id"], ps[1]["status"], ps[1]["why"]), ("trivy-image", "skipped", "add --images"))
        self.assertEqual(SR.status_label(ps[1]), "skipped — add --images")
        off = ST.detect(self.repo, lambda n: "/bin/" + n, False, True)
        self.assertIn("--skip-check-update", off[0]["argv"])
        self.assertEqual((off[1]["status"], off[1]["why"], off[1]["target"]), ("skipped", SC.WHY_NET, "alpine:3.19"))

    def test_image_plans_refs(self):   # R2
        self.w("Dockerfile", "ARG V=1\nFROM --platform=linux/amd64 golang:1.22 AS build\nFROM build\nFROM scratch\n"
                             "FROM gcr.io/distroless/static:nonroot\n")
        self.w("svc/compose.yaml", "services:\n  db:\n    image: \"postgres:16\"\n  web:\n    image: golang:1.22\n")
        ps = [p for p in ST.detect(self.repo, lambda n: "/bin/" + n, True, True) if p["id"] == "trivy-image"]
        self.assertEqual([(p["target"], p["at"]) for p in ps], [("golang:1.22", ("Dockerfile", 2)),
                                                               ("gcr.io/distroless/static:nonroot", ("Dockerfile", 5)),
                                                               ("postgres:16", ("svc/compose.yaml", 3))])
        self.assertEqual(ps[0]["argv"], ["/bin/trivy", "image", "--scanners", "vuln", "--image-src", "docker,remote",
                                         "--format", "json", "--quiet", "--", "golang:1.22"])

    def test_bad_refs_refused(self):
        self.w("Dockerfile", "ARG B\nFROM ${B}:1\nFROM $B\n")
        self.w("compose.yml", "services:\n  a:\n    image: --output=/tmp/x\n")
        ps = [p for p in ST.detect(self.repo, lambda n: "/bin/" + n, True, True) if p["id"] == "trivy-image"]
        self.assertEqual([(p["status"], p["why"]) for p in ps], [("skipped", ST.WHY_ARG), ("skipped", ST.WHY_BAD)])
        self.assertFalse(any("argv" in p for p in ps))
        self.assertIsNone(ST.REF_RE.fullmatch("-x"))


    def test_compose_build_service_skipped(self):   # C1: a locally built tag is not a registry image
        self.w("compose.yml", "services:\n  app:\n    build: .\n    image: myapp:latest\n  db:\n    image: postgres:16\n"
                              "  web:\n    image: nginx:1\n    build:\n      context: web\n")
        self.assertEqual([r["ref"] for r in ST.refs(self.repo)], ["postgres:16"])

    def test_heredoc_and_continuation_not_from(self):   # C2
        self.w("Dockerfile", "FROM python:3.12\nRUN <<EOF\nfrom os import path\nEOF\nRUN echo a \\\n    from x import y\n"
                             "RUN cat <<-'PY' > a.py\n\tfrom z import w\n\tPY\nFROM alpine:3.19\n")
        self.assertEqual([(r["ref"], r["line"]) for r in ST.refs(self.repo)], [("python:3.12", 1), ("alpine:3.19", 10)])


class Parse(Tmp):
    def test_config(self):
        its = ST.parse_config(json.dumps(CONFIG))
        self.assertEqual(its, [{"file": "Dockerfile", "line": 3, "rule": "DS002", "sev": "high",
                                "help": {"desc": "Image user should not be root",
                                         "url": "https://avd.aquasec.com/misconfig/ds002"}}])
        with self.assertRaises(ValueError):
            ST.parse_config("not json")

    def test_image_fix_flag(self):   # R5
        its = ST.parse_image(json.dumps(image(("CVE-2024-0001", "openssl", "CRITICAL", True),
                                              ("CVE-2024-0002", "zlib", "HIGH", False), ("CVE-2024-0003", "tar", "LOW", False))))
        self.assertEqual([(x["rule"], x["pkg"], x["sev"], x["fix"], x["file"]) for x in its],
                         [("CVE-2024-0001", "openssl", "critical", True, ""), ("CVE-2024-0002", "zlib", "high", False, ""),
                          ("CVE-2024-0003", "tar", "low", False, "")])
        self.assertEqual(ST.counts(its), (1, 1))
        self.assertNotIn(LEAK[1], json.dumps(its))
        self.assertNotIn(LEAK[3], json.dumps(its))

    def test_merge_dedupes_across_images(self):   # R2
        a = dict(tool="trivy-image", file="Dockerfile", line=1, rule="CVE-2024-0001", pkg="openssl", sev="medium", fix=False, img="a:1")
        b = dict(a, sev="critical", fix=True, img="b:1", file="compose.yml")
        c = dict(tool="bandit", file="x.py", line=2, rule="B105", sev="low")
        out = ST.merge([a, b, c, dict(a, rule="CVE-2024-0009")])
        self.assertEqual(out[0], c)
        m = out[1]
        self.assertEqual((m["rule"], m["sev"], m["imgs"], m["fix"], m["file"]), ("CVE-2024-0001", "critical", 2, True, "Dockerfile"))
        self.assertNotIn("img", m)
        self.assertEqual(out[2]["imgs"], 1)
        many = [dict(a, rule="CVE-2024-%04d" % i) for i in range(ST.IMG_ITEMS_MAX + 5)]
        self.assertEqual(len(ST.merge(many)), ST.IMG_ITEMS_MAX)

    def test_fail_why(self):   # R6
        p = {"id": "trivy-image", "target": "ghcr.io/org/app:1"}
        why = lambda err, plan=p: ST.fail_why(plan, {"rc": 1, "err": err, "out": ""})
        self.assertEqual(why("GET https://ghcr.io/v2/: UNAUTHORIZED: authentication required"), "docker login ghcr.io needed")
        self.assertEqual(why("403 Forbidden", dict(p, target="alpine:3")), "docker login docker.io needed")
        self.assertEqual(why("denied", dict(p, target="localhost:5000/x")), "docker login localhost:5000 needed")
        self.assertEqual(why("MANIFEST_UNKNOWN: manifest unknown"), ST.WHY_NOT_FOUND)
        self.assertEqual(why("init error: DB error: failed to download vulnerability DB: denied"), ST.WHY_DB)
        self.assertEqual(why("failed to download checks bundle", {"id": "trivy-config"}), ST.WHY_CHECKS)
        self.assertIsNone(why("something else"))
        self.assertIsNone(ST.fail_why(p, {"rc": 0, "err": "UNAUTHORIZED"}))
        self.assertTrue(all(len(w) <= AC.WHY_MAX for w in (ST.WHY_DB, ST.WHY_CHECKS, ST.WHY_NOT_FOUND)))

    def test_judge_fail_never_clean(self):   # R6: auth / DB failure is a reason row
        self.w("Dockerfile", "FROM alpine:3.19\n")
        p = {"id": "trivy-image", "src": "stdout", "ok_rc": (0,), "net": True, "target": "alpine:3.19",
             "at": ("Dockerfile", 1), "cwd": self.repo}
        st, why, its, nf = AC.judge(p, {"rc": 1, "out": "", "err": "failed to download vulnerability DB"}, self.repo)
        self.assertEqual((st, why, its, nf), ("fail", ST.WHY_DB, [], 0))
        st, why, its, nf = AC.judge(p, {"rc": 1, "out": "", "err": "dial tcp: no such host UNAUTHORIZED"}, self.repo)
        self.assertEqual((st, why), ("fail", "docker login docker.io needed"))
        st, why, its, nf = AC.judge(p, {"rc": 0, "out": json.dumps(image(("CVE-2024-0001", "openssl", "HIGH", True))),
                                        "err": ""}, self.repo)
        self.assertEqual((st, nf, its[0]["file"], its[0]["line"], its[0]["img"]), ("ok", 1, "Dockerfile", 1, "alpine:3.19"))


class Run(Tmp):
    def test_runner_images(self):
        spec = importlib.util.spec_from_file_location("arch_checks_cli_trivy", os.path.join(ROOT, "scripts", "arch_checks.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        store = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-trivy-store-"))
        self.addCleanup(shutil.rmtree, store, True)
        self.w("Dockerfile", "FROM alpine:3.19\nUSER root\n")
        self.w("compose.yml", "services:\n  a:\n    image: debian:12\n  b:\n    image: ghcr.io/org/private:1\n")
        outs = {"alpine:3.19": image(("CVE-2024-0001", "openssl", "HIGH", True), ("CVE-2024-0002", "zlib", "CRITICAL", False)),
                "debian:12": image(("CVE-2024-0001", "openssl", "CRITICAL", False))}
        seen, err = [], ["UNAUTHORIZED: " + LEAK[0]]

        def ex(p, t, tmp):
            seen.append(p["argv"])
            if p["argv"][1] == "config":
                return {"rc": 0, "out": json.dumps(CONFIG), "err": "", "t0": 0, "ms": 1}
            ref = p["argv"][-1]
            if ref not in outs:
                return {"rc": 1, "out": "", "err": err[0], "t0": 0, "ms": 1}
            return {"rc": 0, "out": json.dumps(outs[ref]), "err": "", "t0": 0, "ms": 1}
        git = lambda repo, args: ("a" * 40 + "\n") if args[0] == "rev-parse" else ""
        with mock.patch.object(AV, "ARCH_DIR", store), mock.patch.object(cli, "_git", git), \
                mock.patch.object(cli, "_which", lambda n: "/bin/" + n if n == "trivy" else None), \
                mock.patch.object(cli, "_exec", ex), mock.patch.object(cli, "_probe", lambda: True), \
                mock.patch.object(cli, "_export", lambda r, h, d, t: shutil.copytree(r, d, dirs_exist_ok=True) and True), \
                mock.patch.object(cli.time, "time", lambda: 1760000000.0):
            self.assertEqual(cli._args(["--verify", "--last", "--category", "security", "--images"]), None)
            self.assertEqual(cli._args(["--log-show", "--last", "--images"]), None)
            self.assertTrue(cli._args(["--repo", self.repo, "--category", "security", "--images"])["images"])
            rc, line = cli.run(self.repo, images=True)
            fp = os.path.join(AV.store_dir(self.repo, "a" * 40), SC.SEC_FILE)
            j = AV.read_json(fp)
            kdir = os.path.dirname(os.path.dirname(fp))
            md = SR.read_text(kdir, SR.newest(kdir))
            self.assertEqual(cli.verify(self.repo, "a" * 40)[0], 0)
            ran = lambda: [r for r in SC.log_read(kdir) if r["src"] == "scan"][-1]["tools"]
            self.assertNotIn("trivy-image", ran())   # auth failure: old image findings stay open
            err[0] = "MANIFEST_UNKNOWN: manifest unknown"
            cli.run(self.repo, images=True)
            self.assertIn("trivy-image", ran())      # C1: not found is a reason row, not a failed scan
        self.assertEqual(rc, 0)
        self.assertEqual(AC.checks_errors(j, self.repo, "a" * 40, SC.SEC_IDS), [])
        rows = [(t["id"], t["status"], t.get("target"), t.get("fixable"), t.get("waiting"), t.get("why")) for t in j["tools"]
                if t["id"] in ST.IDS]
        self.assertEqual(rows, [("trivy-config", "ok", None, None, None, None),
                                ("trivy-image", "ok", "alpine:3.19", 1, 1, None),
                                ("trivy-image", "ok", "debian:12", 0, 1, None),
                                ("trivy-image", "fail", "ghcr.io/org/private:1", None, None, "docker login ghcr.io needed")])
        img = {x["rule"]: x for x in j["items"] if x["tool"] == "trivy-image"}
        self.assertEqual((img["CVE-2024-0001"]["imgs"], img["CVE-2024-0001"]["sev"], img["CVE-2024-0001"]["fix"]),
                         (2, "critical", True))
        self.assertEqual(sum(t["n"]["critical"] for t in j["tools"]), 2)   # merged, counted once
        self.assertIn("`alpine:3.19`: fixable high/critical 1 — replace base image · waiting 1 (no fix yet)", md)
        self.assertIn("`ghcr.io/org/private:1`: failed — docker login ghcr.io needed", md)
        self.assertTrue(all(a.index("--") == len(a) - 2 for a in seen if a[1] == "image"))
        blob = json.dumps(j) + md
        for leak in LEAK:
            self.assertNotIn(leak, blob)


class Counts(unittest.TestCase):
    def test_first_ok_row_carries_n(self):   # C4
        rows = [{"id": "trivy-image", "rules": "default", "status": "skipped", "why": "invalid image reference"},
                {"id": "trivy-image", "rules": "default", "status": "ok", "target": "a:1"},
                {"id": "trivy-image", "rules": "default", "status": "ok", "target": "b:1"}]
        it = {"tool": "trivy-image", "file": "Dockerfile", "line": 1, "rule": "CVE-2024-0001", "sev": "high"}
        j = AC.build("/r", "a" * 40, False, False, 1.0, rows, [it])
        self.assertEqual([t["n"]["high"] for t in j["tools"]], [0, 1, 0])


if __name__ == "__main__":
    unittest.main()
