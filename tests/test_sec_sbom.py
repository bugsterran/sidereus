"""sidereus/sec_sbom.py (syft SBOM + grype SCA): plans, SBOM checks, the grype parser (fixture JSON in grype 0.121
`-o json --by-cve` shape), the judge, the checks-file summary and one runner run with both tools stubbed
(no live tool, clock or network)."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._fs import assert_mode
from tests._load import sidereus, ROOT

SB = sidereus("sec_sbom")
SC = sidereus("sec_checks")
AC = sidereus("arch_checks")
AV = sidereus("arch_verify")
LEAK = ("PLANTED-DESCRIPTION", "https://planted.example/advisory", "PLANTED-MATCHER", "pkg:pypi/planted")
HEAD = "b" * 40


def match(cve, name, ver, sev, fix=(), path="/requirements.txt", rel=()):
    return {"vulnerability": {"id": cve, "severity": sev, "description": LEAK[0], "urls": [LEAK[1]],
                              "fix": {"versions": list(fix), "state": "fixed" if fix else "not-fixed"}},
            "relatedVulnerabilities": [{"id": r, "description": LEAK[0]} for r in rel],
            "matchDetails": [{"matcher": LEAK[2]}],
            "artifact": {"name": name, "version": ver, "purl": LEAK[3],
                         "locations": [{"path": path, "accessPath": path}] if path else []}}


def grype(ms, built="2026-11-12T06:20:58Z", old=False):
    db = {"built": built} if old else {"status": {"schemaVersion": "v6.1.10", "built": built, "valid": True}}
    return json.dumps({"matches": ms, "source": {}, "descriptor": {"name": "grype", "version": "0.121.3",
                                                                   **({"db": db} if built else {})}})


def cdx(comps):
    """comps: (type, name, version, path[, purl])."""
    return json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.7", "components": [
        dict({"type": c[0], "name": c[1], "version": c[2], "properties": [{"name": "syft:location:0:path", "value": c[3]}]},
             **({"purl": c[4]} if len(c) > 4 else {}))
        for c in comps]})

MVN = [("library", "spring-web", "UNKNOWN", "/pom.xml", "pkg:maven/org.springframework/spring-web"),
       ("library", "spring-core", "", "/pom.xml", "pkg:maven/org.springframework/spring-core"),
       ("library", "spring-beans", "5.3.39", "/pom.xml", "pkg:maven/org.springframework/spring-beans@5.3.39"),
       ("library", "left-pad", "UNKNOWN", "/package.json", "pkg:npm/left-pad")]


class Tmp(unittest.TestCase):
    def setUp(self):
        self.repo = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-sbom-"))
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-sbom-tmp-"))
        self.addCleanup(shutil.rmtree, self.repo, True)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def w(self, rel, text, root=None):
        fp = os.path.join(root or self.repo, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)
        return fp

    def plans(self, net=True, which=None):
        wh = which or (lambda n: "/bin/" + n if n in SB.IDS else None)
        return {p["id"]: p for p in SB.detect(self.repo, wh, net, "k" * 16, HEAD)}


class Detect(Tmp):
    def test_missing_both(self):   # R3: missing like the other tools
        p = self.plans(which=lambda n: None)
        self.assertEqual((p["syft"]["status"], p["grype"]["status"]), ("missing", "missing"))
        self.assertTrue(p["syft"]["why"].startswith("install: "))
        self.assertEqual([x["id"] for x in SB.detect(self.repo, lambda n: None, True, "k", HEAD)], ["syft", "grype"])

    def test_offline(self):   # R3 R5: syft still runs without network; grype skipped, never 0 issues
        self.w("pom.xml", "<project/>")
        p = self.plans(net=False)
        self.assertNotIn("status", p["syft"])
        self.assertFalse(p["syft"]["net"])
        self.assertEqual(p["syft"]["env"]["SYFT_JAVA_USE_NETWORK"], "false")
        self.assertEqual(p["syft"]["notes"], ["mvn-offline"])
        self.assertEqual((p["grype"]["status"], p["grype"]["why"]), ("skipped", SC.WHY_NET))

    def test_maven_online_env(self):   # R5: Maven Central POM lookup, positive parent depth, no local repo
        self.w("svc/pom.xml", "<project/>")
        p = self.plans()["syft"]
        self.assertTrue(p["net"])
        self.assertEqual(p["notes"], [])
        e = p["env"]
        self.assertEqual((e["SYFT_JAVA_USE_NETWORK"], e["SYFT_JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES"],
                          e["SYFT_JAVA_USE_MAVEN_LOCAL_REPOSITORY"], e["SYFT_CHECK_FOR_APP_UPDATE"]),
                         ("true", "true", "false", "false"))
        self.assertGreater(int(e["SYFT_JAVA_MAX_PARENT_RECURSIVE_DEPTH"]), 0)
        self.assertNotIn("SYFT_JAVA_MAVEN_URL", e)

    def test_no_pom_never_online(self):   # R5: only a pom.xml makes syft use the network
        self.w("requirements.txt", "requests==2.19.0\n")
        p = self.plans()["syft"]
        self.assertFalse(p["net"])
        self.assertEqual(p["env"]["SYFT_JAVA_USE_NETWORK"], "false")
        self.assertNotIn("SYFT_JAVA_MAX_PARENT_RECURSIVE_DEPTH", p["env"])

    def test_gradle_without_lock(self):   # R5
        self.w("app/build.gradle.kts", "")
        self.assertEqual(self.plans()["syft"]["notes"], ["gradle-no-lock"])
        self.w("app/gradle.lockfile", "")
        self.assertEqual(self.plans()["syft"]["notes"], [])

    def test_bind_argv(self):   # R1 R5: argv[0] is the binary, cwd is the temp dir, outputs land in it
        p = self.plans()
        s, g = SB.bind(p["syft"], self.tmp), SB.bind(p["grype"], self.tmp)
        self.assertEqual(s["argv"], ["/bin/syft", "scan", "dir:" + self.repo, "-q", "--source-name", "k" * 16,
                                     "--source-version", HEAD,
                                     "-o", "cyclonedx-json=" + os.path.join(self.tmp, SB.SBOM_FILE),
                                     "-o", "syft-json=" + os.path.join(self.tmp, SB.SYFT_JSON)])
        self.assertEqual(g["argv"], ["/bin/grype", "sbom:" + os.path.join(self.tmp, SB.SYFT_JSON), "--by-cve", "-o", "json"])
        self.assertEqual((s["cwd"], g["cwd"]), (self.tmp, self.tmp))
        self.assertEqual(g["env"]["GRYPE_CHECK_FOR_APP_UPDATE"], "false")
        for a in (s["argv"], g["argv"]):
            self.assertFalse(any(x in ("mvn", "gradle", "gradlew", "./gradlew") for x in a))

    def test_bad_ident_not_passed(self):
        p = SB.detect(self.repo, lambda n: "/bin/" + n, True, "-x --evil", "not a sha")[0]
        self.assertEqual((p["name"], p["ver"]), ("repo", "unknown"))


class Sbom(Tmp):
    def plan(self):
        return SB.bind(self.plans()["syft"], self.tmp)

    def test_state(self):   # R2: components without type file, distinct location paths
        self.w(SB.SBOM_FILE, cdx([("file", "x", "", "/a"), ("library", "requests", "2.19.0", "/requirements.txt"),
                                  ("library", "urllib3", "1.24.1", "/requirements.txt")]), self.tmp)
        self.assertEqual(SB.sbom_state(self.plan()), (2, 1))

    def test_refused(self):
        p = self.plan()
        self.assertIsNone(SB.sbom_state(p))                          # absent
        self.w(SB.SBOM_FILE, json.dumps({"bomFormat": "SPDX"}), self.tmp)
        self.assertIsNone(SB.sbom_state(p))                          # not CycloneDX
        os.remove(os.path.join(self.tmp, SB.SBOM_FILE))
        real = self.w("elsewhere.json", cdx([("library", "a", "1", "/x")]))
        os.symlink(real, os.path.join(self.tmp, SB.SBOM_FILE))
        self.assertIsNone(SB.sbom_state(p))                          # symlink
        os.remove(os.path.join(self.tmp, SB.SBOM_FILE))
        self.w(SB.SBOM_FILE, cdx([("library", "a", "1", "/x")]), self.tmp)
        with mock.patch.object(SB, "SBOM_MAX", 10):
            self.assertIsNone(SB.sbom_state(p))                      # over the cap
        self.w(SB.SBOM_FILE, cdx([]), self.tmp)
        self.assertEqual(SB.sbom_state(p), (0, 0))

    def test_judge_syft(self):   # R2 R3
        p = self.plan()
        self.assertEqual(AC.judge(p, {"rc": 0}, self.repo)[:2], ("fail", SB.WHY_UNREADABLE))
        self.w(SB.SBOM_FILE, cdx([]), self.tmp)
        self.assertEqual(AC.judge(p, {"rc": 0}, self.repo)[:2], ("skipped", SB.WHY_NO_PKGS))
        self.w(SB.SBOM_FILE, cdx([("library", "a", "1", "/x"), ("library", "b", "2", "/y")]), self.tmp)
        self.assertEqual(AC.judge(p, {"rc": 0}, self.repo), ("ok", None, [], 2))
        self.assertEqual(AC.judge(p, {"rc": 1}, self.repo)[:2], ("fail", "exit 1"))

    def test_unresolved_maven(self):   # R5: Maven components without a version are flagged, online or offline
        self.w("pom.xml", "<project/>")
        self.w(SB.SBOM_FILE, cdx(MVN), self.tmp)
        p = self.plan()
        self.assertEqual(SB.sbom_doc(p)[1:], (4, 2, 2))   # the npm UNKNOWN is not a Maven component
        self.assertEqual(SB.notes(p, {"err": ""}, 2), ["mvn-unresolved"])
        off = SB.bind(self.plans(net=False)["syft"], self.tmp)
        self.assertEqual(SB.notes(off, {"err": ""}, 2), ["mvn-offline", "mvn-unresolved"])
        self.w(SB.SBOM_FILE, cdx(MVN[2:3]), self.tmp)
        self.assertEqual(SB.sbom_doc(p)[3], 0)
        self.assertEqual(SB.notes(p, {"err": ""}, 0), [])

    def test_notes_net_error(self):   # R5: a network error on stderr flags an online pom.xml run
        self.w("pom.xml", "<project/>")
        p = self.plan()
        self.assertEqual(SB.notes(p, {"err": ""}), [])
        self.assertEqual(SB.notes(p, {"err": "dial tcp: lookup repo.maven.apache.org: no such host"}), ["mvn-offline"])


class Grype(Tmp):
    def test_parse_fields_only(self):   # R1: no tool message text, only the allow-listed fields
        out = SB.parse_grype(grype([
            match("CVE-2018-18074", "requests", "2.19.0", "High", ["2.20.0"], rel=["GHSA-x84v-xcm2-53pg", "CVE-2018-18074"]),
            match("CVE-2018-18074", "requests", "2.19.0", "High", ["2.20.0"]),            # duplicate
            match("CVE-2020-0001", "lib", "1.0", "Negligible", ["not a version!"]),
            match("CVE-2020-0002", "lib", "1.0", "Unknown", path=None),
            match("GHSA-aaaa-bbbb-cccc", "lib", "1.0", "Critical", ["1.1", "1.2"], rel=["CVE-2020-0003"])]))
        self.assertEqual(out[0], {"file": "requirements.txt", "line": 1, "rule": "CVE-2018-18074", "sev": "high",
                                  "pkg": "requests", "ver": "2.19.0", "fixv": "2.20.0"})
        self.assertEqual(len(out), 4)
        self.assertEqual((out[1]["sev"], "fixv" in out[1]), ("low", False))
        self.assertEqual((out[2]["sev"], out[2]["file"]), ("medium", ""))
        self.assertEqual((out[3]["fixv"], out[3]["cve"]), ("1.1", ["CVE-2020-0003"]))
        blob = json.dumps(out)
        for leak in LEAK:
            self.assertNotIn(leak, blob)
        with self.assertRaises(ValueError):
            SB.parse_grype("[]")

    def test_db_built(self):   # R6: v6 and older shapes; absent or malformed stays absent
        self.assertEqual(SB.db_built(grype([])), "2026-11-12T06:20:58Z")
        self.assertEqual(SB.db_built(grype([], old=True)), "2026-11-12T06:20:58Z")
        self.assertIsNone(SB.db_built(grype([], built=None)))
        self.assertIsNone(SB.db_built(grype([], built="0")))
        self.assertIsNone(SB.db_built("not json"))

    def test_judge_db_and_net(self):   # R3: DB / network failures are skipped, never ok
        p = SB.bind(self.plans()["grype"], self.tmp)
        db = {"rc": 1, "out": "", "err": "[0000] ERROR failed to load vulnerability db: database does not exist"}
        self.assertEqual(AC.judge(p, db, self.repo)[:2], ("skipped", SB.WHY_DB))
        old = {"rc": 1, "out": "", "err": "the vulnerability database was built 9 days ago (max allowed age is 5 days)"}
        self.assertEqual(AC.judge(p, old, self.repo)[:2], ("skipped", SB.WHY_DB))
        net = {"rc": 1, "out": "", "err": "dial tcp: lookup grype.anchore.io: no such host"}
        self.assertEqual(AC.judge(p, net, self.repo)[:2], ("skipped", SC.WHY_NET_FAIL))
        self.assertEqual(AC.judge(p, {"rc": 2, "out": "", "err": ""}, self.repo)[0], "fail")

    def test_judge_items(self):   # R4: tool id grype, location-less matches dropped and counted
        self.w("requirements.txt", "requests==2.19.0\n")
        p = dict(SB.bind(self.plans()["grype"], self.tmp), sbom_files=3)
        st, why, its, nf = AC.judge(p, {"rc": 0, "out": grype([match("CVE-2018-18074", "requests", "2.19.0", "High", ["2.20.0"]),
                                                               match("CVE-2020-0002", "x", "1", "Low", path=None),
                                                               match("CVE-2020-0004", "y", "1", "Low", path="/gone.txt")])},
                                   self.repo)
        self.assertEqual((st, why, nf), ("ok", "1 matches without a file", 3))
        self.assertEqual([(x["tool"], x["file"], x["rule"]) for x in its], [("grype", "requirements.txt", "CVE-2018-18074")])


def _row(tid, st="ok", **kw):
    return dict({"id": tid, "rules": "default", "status": st, "ms": 1, "files": 1}, **kw)


def _it(tool, rule, sev, pkg=None, ver=None, fixv=None, f="requirements.txt"):
    x = {"tool": tool, "file": f, "line": 1, "rule": rule, "sev": sev}
    x.update({k: v for k, v in (("pkg", pkg), ("ver", ver), ("fixv", fixv)) if v})
    return x


class Summary(unittest.TestCase):
    def build(self, tools, items):
        return AC.build("/r", HEAD, False, False, 1.0, tools, items)

    def test_summary(self):   # R6: categories, severity totals, DB time, fixes grouped by package
        items = [_it("grype", "CVE-2024-0001", "high", "urllib3", "1.24.1", "1.24.2"),
                 _it("grype", "CVE-2024-0002", "critical", "urllib3", "1.24.1", "1.26.18"),
                 _it("grype", "CVE-2024-0003", "medium", "urllib3", "1.24.1", "1.26.9"),
                 _it("grype", "CVE-2024-0004", "low", "urllib3", "1.24.1"),
                 _it("grype", "CVE-2024-0005", "medium", "requests", "2.19.0", "2.20.0"),
                 _it("osv-scanner", "GHSA-x84v-xcm2-53pg", "high", "requests"),
                 _it("gitleaks", "aws-key", "high", f="a.py")]
        j = self.build([_row("syft", components=2, notes=["gradle-no-lock"]), _row("grype", db_built="2026-11-12T06:20:58Z"),
                        _row("osv-scanner"), _row("gitleaks"), _row("semgrep", "missing")], items)
        s = j["summary"]
        self.assertEqual(s["cat"], {"cve": 6, "sast": None, "secret": 1, "config": None})   # no sast tool ran: unknown
        self.assertEqual(s["sev"], {"critical": 1, "high": 3, "medium": 2, "low": 1})
        self.assertEqual(s["db_built"], "2026-11-12T06:20:58Z")
        self.assertEqual(s["fixes"], [{"pkg": "urllib3", "ver": "1.24.1", "to": "1.26.18", "n": 3, "sev": "critical"},
                                      {"pkg": "requests", "ver": "2.19.0", "to": "2.20.0", "n": 1, "sev": "medium"}])
        self.assertNotIn("fixes_more", s)
        self.assertEqual([(t["id"], t.get("components"), t.get("notes"), t.get("db_built")) for t in j["tools"][:2]],
                         [("syft", 2, ["gradle-no-lock"], None), ("grype", None, None, "2026-11-12T06:20:58Z")])
        g = [x for x in j["items"] if x["tool"] == "grype"][0]
        self.assertEqual((g["ver"], g["fixv"]), ("1.24.1", "1.26.18"))
        self.assertNotIn("ver", [x for x in j["items"] if x["tool"] == "osv-scanner"][0])
        self.assertEqual(AC.checks_errors(j, None, HEAD, SC.SEC_IDS), [])

    def test_nothing_ran_is_unknown(self):   # unknown is not zero
        s = self.build([_row("grype", "skipped", why=SC.WHY_NET)], [])["summary"]
        self.assertEqual(s["sev"], {"critical": None, "high": None, "medium": None, "low": None})
        self.assertEqual(set(s["cat"].values()), {None})
        self.assertNotIn("db_built", s)

    def test_only_syft_ok_is_unknown(self):   # syft finds packages, not issues: no «Critical 0»
        s = self.build([_row("syft", components=3), _row("grype", "skipped", why=SB.WHY_DB)], [])["summary"]
        self.assertEqual(s["sev"], {"critical": None, "high": None, "medium": None, "low": None})
        self.assertEqual(set(s["cat"].values()), {None})

    def test_fixes_cap_and_order(self):   # R6: FIXES_MAX, groups left out counted, natural version order
        items = [_it("grype", "CVE-2024-%04d" % i, "low", "p%02d" % i, "1.0", "1.0.%d" % i) for i in range(SB.FIXES_MAX + 3)]
        items += [_it("grype", "CVE-2025-0001", "high", "z", "1.0", "1.9"), _it("grype", "CVE-2025-0002", "high", "z", "1.0", "1.10"),
                  _it("grype", "CVE-2025-0003", "high", "z", "1.0", "1.10.0-rc1")]
        s = self.build([_row("grype")], items)["summary"]
        self.assertEqual(len(s["fixes"]), SB.FIXES_MAX)
        self.assertEqual(s["fixes_more"], 4)
        self.assertEqual(s["fixes"][0], {"pkg": "z", "ver": "1.0", "to": "1.10", "n": 3, "sev": "high"})
        self.assertEqual(AC.checks_errors(self.build([_row("grype")], items), None, HEAD, SC.SEC_IDS), [])

    def test_gate_strict(self):   # R6: off-contract summary / rows / items fail the gate
        good = self.build([_row("syft", components=2), _row("grype")], [_it("grype", "CVE-2024-0001", "high", "a", "1", "2")])
        bad = [("summary", lambda j: j["summary"]["cat"].update(cve=-1)),
               ("summary", lambda j: j["summary"].update(text="x")),
               ("summary", lambda j: j["summary"].update(fixes_more=0)),
               ("summary", lambda j: j["summary"].update(db_built="yesterday")),
               ("summary", lambda j: j["summary"]["fixes"][0].update(to="2; rm")),
               ("tools[0]", lambda j: j["tools"][0].update(notes=["free text"])),
               ("tools[1]", lambda j: j["tools"][1].update(components=3)),       # components on a grype row
               ("tools[0]", lambda j: j["tools"][0].update(db_built="2026-11-12T06:20:58Z")),
               ("tools[0]", lambda j: j["tools"][0].update(unresolved=2)),           # count without its note
               ("tools[0]", lambda j: j["tools"][0].update(notes=["mvn-unresolved"], unresolved=0)),
               ("tools[1]", lambda j: j["tools"][1].update(notes=["mvn-unresolved"], unresolved=2)),
               ("items", lambda j: j["items"][0].update(fixv="bad version!")),
               ("items", lambda j: j["items"].append(dict(_it("osv-scanner", "GHSA-x", "high", "a"), ver="1")))]
        for err, mut in bad:
            j = json.loads(json.dumps(good))
            mut(j)
            self.assertIn(err, AC.checks_errors(j, None, HEAD, SC.SEC_IDS), err)
        j = json.loads(json.dumps(good))
        del j["summary"]
        self.assertEqual(AC.checks_errors(j, None, HEAD, SC.SEC_IDS), [])   # older files still pass

    def test_categories_cover_ids(self):
        self.assertEqual(set(SC.CATEGORY) | {"syft"}, set(SC.SEC_IDS))
        self.assertTrue(set(SC.CATEGORY.values()) <= set(SC.CAT_KEYS))


class Load(Tmp):
    def store(self, j):
        d = os.path.join(self.tmp, "k", HEAD)
        os.makedirs(d)
        with open(os.path.join(d, SC.SEC_FILE), "w", encoding="utf-8") as f:
            json.dump(j, f)
        return os.path.join(self.tmp, "k", "map")

    def test_loader(self):   # R2 R4 R6: counts, summary and grype items beside osv-scanner reach the page
        items = [_it("grype", "CVE-2024-0001", "high", "requests", "2.19.0", "2.20.0"),
                 _it("osv-scanner", "GHSA-x84v-xcm2-53pg", "high", "requests")]
        j = AC.build(self.repo, HEAD, False, False, 1.0, [_row("syft", components=12, notes=["mvn-offline", "mvn-unresolved"], unresolved=3),
                                                          _row("grype", db_built="2026-11-12T06:20:58Z"), _row("osv-scanner")], items)
        s = AC._load_one(self.repo, self.store(j), {}, HEAD, SC.SEC_FILE, SC.SEC_IDS)
        t = {x["id"]: x for x in s["tools"]}
        self.assertEqual((t["syft"]["components"], t["syft"]["notes"], t["syft"]["unresolved"], t["grype"]["db_built"]),
                         (12, ["mvn-offline", "mvn-unresolved"], 3, "2026-11-12T06:20:58Z"))
        self.assertEqual(AC.checks_errors(j, self.repo, HEAD, SC.SEC_IDS), [])
        self.assertEqual(sorted(x["tool"] for x in s["top"]), ["grype", "osv-scanner"])
        g = [x for x in s["top"] if x["tool"] == "grype"][0]
        self.assertEqual((g["pkg"], g["ver"], g["fixv"]), ("requests", "2.19.0", "2.20.0"))
        self.assertEqual(s["summary"], j["summary"])

    def test_old_file_no_summary(self):   # R6: nothing shown, not zeros
        j = AC.build(self.repo, HEAD, False, False, 1.0, [_row("osv-scanner")], [])
        del j["summary"]
        self.assertNotIn("summary", AC._load_one(self.repo, self.store(j), {}, HEAD, SC.SEC_FILE, SC.SEC_IDS))


class Run(Tmp):
    def cli(self):
        spec = importlib.util.spec_from_file_location("arch_checks_cli_sbom", os.path.join(ROOT, "scripts", "arch_checks.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        return cli

    def run_once(self, cli, store, offline=False, only=None, grype_out=None, comps=None, which=SB.IDS):
        seen = []

        def ex(p, t, tmp):
            seen.append(p)
            if p["argv"][0] == "/bin/syft":
                for a in p["argv"]:
                    if a.startswith("cyclonedx-json="):
                        with open(a.split("=", 1)[1], "w", encoding="utf-8") as f:
                            f.write(cdx(comps if comps is not None else
                                        [("library", "requests", "2.19.0", "/requirements.txt")]))
                return {"rc": 0, "out": "", "err": "", "t0": 0, "ms": 1}
            return {"rc": 0, "out": grype_out or grype([match("CVE-2018-18074", "requests", "2.19.0", "High", ["2.20.0"])]),
                    "err": "", "t0": 0, "ms": 1}
        git = lambda repo, args: (HEAD + "\n") if args[0] == "rev-parse" else ""
        with mock.patch.object(AV, "ARCH_DIR", store), mock.patch.object(cli, "_git", git), \
                mock.patch.object(cli, "_which", lambda n: "/bin/" + n if n in which else None), \
                mock.patch.object(cli, "_exec", ex), mock.patch.object(cli, "_probe", lambda: True), \
                mock.patch.object(cli, "_export", lambda r, h, d, t: shutil.copytree(r, d, dirs_exist_ok=True) and True), \
                mock.patch.object(cli.time, "time", lambda: 1760000000.0):
            rc, line = cli.run(self.repo, only=only, offline=offline)
            d = AV.store_dir(self.repo, HEAD)
            j = AV.read_json(os.path.join(d, SC.SEC_FILE))
            ok = cli.verify(self.repo, HEAD)[0]
        return rc, line, j, d, seen, ok

    def setUp(self):
        super().setUp()
        self.store = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-sbom-store-"))
        self.addCleanup(shutil.rmtree, self.store, True)
        self.w("requirements.txt", "requests==2.19.0\n")

    def test_run(self):   # R1 R2 R4
        cli = self.cli()
        rc, line, j, d, seen, ok = self.run_once(cli, self.store)
        self.assertEqual((rc, ok), (0, 0))
        self.assertEqual(AC.checks_errors(j, self.repo, HEAD, SC.SEC_IDS), [])
        t = {x["id"]: x for x in j["tools"]}
        self.assertEqual((t["syft"]["status"], t["syft"]["components"], t["grype"]["status"], t["grype"]["files"]),
                         ("ok", 1, "ok", 1))
        self.assertEqual(t["grype"]["db_built"], "2026-11-12T06:20:58Z")
        self.assertIn(" · sbom 1 components", line)
        g = [x for x in j["items"] if x["tool"] == "grype"]
        self.assertEqual([(x["file"], x["rule"], x["pkg"], x["ver"], x["fixv"], x["sev"]) for x in g],
                         [("requirements.txt", "CVE-2018-18074", "requests", "2.19.0", "2.20.0", "high")])
        with open(os.path.join(d, SB.SBOM_FILE), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["bomFormat"], "CycloneDX")
        assert_mode(self, os.path.join(d, SB.SBOM_FILE), 0o644)
        self.assertEqual([p["argv"][0] for p in seen], ["/bin/syft", "/bin/grype"])
        self.assertTrue(all(p["cwd"] == p["tmp"] and p["cwd"] != self.repo for p in seen))   # repo config never read
        blob = json.dumps(j)
        for leak in LEAK:
            self.assertNotIn(leak, blob)

    def test_offline(self):   # R3 R5
        self.w("pom.xml", "<project/>")
        rc, line, j, d, seen, ok = self.run_once(self.cli(), self.store, offline=True)
        t = {x["id"]: x for x in j["tools"]}
        self.assertEqual((t["syft"]["status"], t["syft"]["notes"]), ("ok", ["mvn-offline"]))
        self.assertEqual((t["grype"]["status"], t["grype"]["why"]), ("skipped", SC.WHY_NET))
        self.assertEqual(seen[0]["env"]["SYFT_JAVA_USE_NETWORK"], "false")

    def test_no_packages_skips_grype(self):   # R3: no SBOM to match
        rc, line, j, d, seen, ok = self.run_once(self.cli(), self.store, comps=[])
        t = {x["id"]: x for x in j["tools"]}
        self.assertEqual((t["syft"]["why"], t["grype"]["status"], t["grype"]["why"]),
                         (SB.WHY_NO_PKGS, "skipped", SB.WHY_NO_SBOM))
        self.assertFalse(os.path.exists(os.path.join(d, SB.SBOM_FILE)))
        self.assertEqual(len(seen), 1)

    def test_unresolved_row(self):   # R5: an online pom.xml run whose lookup left versions unresolved says so
        self.w("pom.xml", "<project/>")
        rc, line, j, d, seen, ok = self.run_once(self.cli(), self.store, comps=MVN)
        t = {x["id"]: x for x in j["tools"]}
        self.assertEqual((t["syft"]["notes"], t["syft"]["unresolved"]), (["mvn-unresolved"], 2))
        self.assertEqual(seen[0]["env"]["SYFT_JAVA_USE_NETWORK"], "true")
        self.assertEqual(AC.checks_errors(j, self.repo, HEAD, SC.SEC_IDS), [])
        rc, line, j, d, seen, ok = self.run_once(self.cli(), self.store)
        self.assertNotIn("unresolved", [x for x in j["tools"] if x["id"] == "syft"][0])

    def test_missing_grype_stays_missing(self):   # R3
        rc, line, j, d, seen, ok = self.run_once(self.cli(), self.store, which=("syft",))
        self.assertEqual([x["status"] for x in j["tools"] if x["id"] == "grype"], ["missing"])

    def test_only_grype_adds_syft(self):
        cli = self.cli()
        self.assertEqual(cli._args(["--repo", self.repo, "--category", "security", "--only", "grype"])["only"], {"grype"})
        rc, line, j, d, seen, ok = self.run_once(cli, self.store, only={"grype"})
        self.assertEqual([x["id"] for x in j["tools"]], ["syft", "grype"])

    def test_no_tests_copy_not_read(self):
        cli = self.cli()
        code = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-sbom-code-"))
        self.addCleanup(shutil.rmtree, code, True)
        with mock.patch.object(cli, "_which", lambda n: "/bin/" + n if n in SB.IDS else None):
            ps = [p for p in cli._plans(self.repo, True, None, False, code, ("k", HEAD)) if p["id"] == "syft"]
        self.assertEqual([p["dir"] for p in ps], [self.repo])


if __name__ == "__main__":
    unittest.main()
