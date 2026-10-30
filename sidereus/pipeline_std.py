"""Standard per-task pipeline drafts («Standard drafts»): data plus one builder. Imports no sidereus modules.

Each entry cites the public practice it follows (src). Roles: P plan · B build · C check · R review · L live · M probe.
"""

# ⚠Must equal pipeline.STAGE_TITLES: those titles take the runner's DEFAULT_TASKS, so they carry no task here.
_REC = ("설계", "구현", "검증", "리뷰", "재검증", "재현", "원인", "수정", "회귀", "트리아지", "라이브 검증", "AI 설정 점검", "프롬프트 검증")
_CC = "https://code.claude.com/docs/en/best-practices"
_CC_DOC = "https://code.claude.com/docs/en/"
_OWASP = "https://cheatsheetseries.owasp.org/cheatsheets/Vulnerable_Dependency_Management_Cheat_Sheet.html"

# (key, title, src, [(stage title, role, optional, onFail (goto, max) | None, task | None)])
STD = (
    ("bugfix", "버그 수정", _CC, [
        ("재현", "M", False, None, None),
        ("원인", "P", False, None, None),
        ("실패 테스트", "C", False, None, "Write a test that fails because of the bug, before any fix. Report the test name and its failure."),
        ("수정", "B", False, None, None),
        ("검증", "C", False, ("수정", 2), None),
        ("리뷰", "R", False, ("수정", 1), None),
        ("라이브 검증", "L", True, None, None)]),
    ("feature", "새 기능", _CC, [
        ("탐색", "P", False, None, "Explore the code the feature touches, read-only. Report the files, entry points and existing patterns to reuse."),
        ("설계", "P", False, None, None),
        ("구현", "B", False, None, None),
        ("검증", "C", False, ("구현", 2), None),
        ("리뷰", "R", False, ("구현", 1), None),
        ("라이브 검증", "L", False, None, None)]),
    ("refactor", "리팩토링", "https://martinfowler.com/bliki/OpportunisticRefactoring.html", [
        ("기준선", "C", False, None, "Run the full test suite before any change and record the result as the baseline. Change nothing."),
        ("계획", "P", False, None, "Plan the refactoring as small behaviour-preserving steps, each one testable on its own."),
        ("리팩토링", "B", False, None, "Apply the planned steps with no behaviour change. Run the tests after each step; on red, revert the step rather than patch it."),
        ("검증", "C", False, ("리팩토링", 2), None),
        ("리뷰", "R", False, ("리팩토링", 1), None)]),
    ("perf", "성능 개선", "https://www.brendangregg.com/methodology.html", [
        ("측정", "M", False, None, "Measure the slow path with a repeatable benchmark. Report the numbers and how to rerun them."),
        ("병목 분석", "M", False, None, "Find the bottleneck from measurements (profile, USE method), not guesses. Report the evidence."),
        ("계획", "P", False, None, "Plan the smallest change that removes the bottleneck and how its effect will be measured."),
        ("최적화", "B", False, None, "Implement the planned optimisation without changing observable behaviour."),
        ("동등성 검증", "C", False, ("최적화", 2), "Run the tests and confirm the output is identical to before the optimisation."),
        ("재측정", "M", False, ("병목 분석", 1), "Rerun the same benchmark. Fail if there is no clear improvement over the first measurement."),
        ("리뷰", "R", True, ("최적화", 1), None)]),
    ("security", "보안 수정", _OWASP, [
        ("영향 평가", "P", False, None, "Assess the vulnerability: affected versions, reachable code paths, exposure and severity."),
        ("재현", "M", True, None, None),
        ("패치", "B", False, None, "Apply the minimal fix or upgrade that removes the vulnerability. Do not widen the change."),
        ("보안·회귀 테스트", "C", False, ("패치", 2), "Add a test proving the vulnerability is closed and run the full suite for regressions."),
        ("보안 리뷰", "R", False, ("패치", 1), "Review the patch for security: input validation, escaping, path and argument checks, secrets."),
        ("배포 확인", "L", False, None, "Confirm the fixed version is what actually runs, and the issue no longer reproduces there.")]),
    ("deps", "의존성 업그레이드", _OWASP, [
        ("조사", "P", False, None, "Read the changelogs between the current and target versions. List breaking changes and advisories."),
        ("버전 올림", "B", False, None, "Bump the dependency versions and lockfile only. No code changes yet."),
        ("깨진 곳 수정", "B", False, None, "Fix the code broken by the upgrade, following the changelog's migration notes."),
        ("전체 테스트", "C", False, ("깨진 곳 수정", 2), "Run the full test suite and build. Report any failure with its cause."),
        ("리뷰", "R", False, ("깨진 곳 수정", 1), None),
        ("라이브 검증", "L", False, None, None)]),
    ("incident", "장애 대응", "https://sre.google/sre-book/managing-incidents/", [
        ("분류", "P", False, None, "Classify the incident: impact, scope, severity, start time. Decide what to mitigate first."),
        ("완화", "B", False, None, "Mitigate first (rollback, disable, failover) before finding the root cause."),
        ("복구 확인", "L", False, ("완화", 1), "Confirm on the live system that service is restored and the symptoms are gone."),
        ("근본 원인", "M", False, None, "Find the root cause from logs, metrics and the timeline. Report evidence, not guesses."),
        ("영구 수정", "B", False, None, "Implement the permanent fix for the root cause, with a test that would have caught it."),
        ("검증", "C", False, ("영구 수정", 2), None),
        ("회고", "R", False, ("영구 수정", 1), "Write a blameless retrospective: timeline, root cause, what went well, action items.")]),
    ("review", "리뷰만", "https://google.github.io/eng-practices/review/reviewer/looking-for.html", [
        ("맥락 파악", "P", False, None, "Read the change and its purpose. Summarise what it does and which files matter. Change nothing."),
        ("리뷰", "R", False, None, None),
        ("지적 검증", "C", True, None, "Check each review finding against the code or tests and mark it confirmed or not.")]),
    # AI-configuration work (hooks · skills · MCP tools): same shape, checked with the «AI config review» / «Prompt check» stages.
    ("hook", "훅 변경", _CC_DOC + "hooks", [
        ("영향 범위", "P", False, None, "List the hook events and matchers this change touches, the other hooks on the same events and their order. Read only; change nothing."),
        ("훅 작성", "B", False, None, "Write or change the hook script and its settings entry. Keep it small; bad or missing input must exit 0 silently."),
        ("훅 실행 시험", "C", False, ("훅 작성", 2), "Run the hook with sample stdin JSON for each event it handles, plus bad and empty input. Fail if it exits non-zero, prints on bad input, blocks a session or runs over its time budget."),
        ("AI 설정 점검", "R", False, ("훅 작성", 1), None),
        ("보안 리뷰", "R", False, ("훅 작성", 1), "Review the hook for security: no secrets or conversation content in its output, safe stdin parsing, path checks. Report findings with file:line."),
        ("실세션 확인", "L", True, None, "Start a fresh session and confirm the hook's effect is visible there.")]),
    ("skill", "스킬 작성·변경", _CC_DOC + "skills", [
        ("범위 정의", "P", False, None, "Define when the skill should trigger, the wording of its description and what it must not do. Read only; change nothing."),
        ("스킬 작성", "B", False, None, "Write or change the skill files to the defined scope. State prohibitions first, cap the output size and give a checkable done-criterion."),
        ("프롬프트 검증", "C", False, ("스킬 작성", 2), None),
        ("AI 설정 점검", "R", False, ("스킬 작성", 1), None),
        ("리뷰", "R", False, ("스킬 작성", 1), None)]),
    ("mcp", "도구·MCP 추가", _CC_DOC + "mcp", [
        ("조사", "P", False, None, "Check overlap with the existing tools and MCP servers and the permissions the new tool needs. Read only; change nothing."),
        ("구현", "B", False, None, None),
        ("계약 테스트", "C", False, ("구현", 2), "Test the tool contract: inputSchema enforced, bad arguments answered with error -32602, bad input never crashes the server, output size bounded."),
        ("보안 리뷰", "R", False, ("구현", 1), "Review the tool for security: secrets masked, path and argument checks, any network use. Report findings with file:line."),
        ("연결 확인", "L", False, None, "Confirm a client lists the new tool and one real call to it works.")]),
)

# role -> R keys to try in order; B tries fix first for these keys
_ROLE_KEYS = {"P": ("design", "triage"), "B": ("build", "fix"), "C": ("check",), "R": ("review",), "L": ("live",), "M": ("probe",)}
_FIX_FIRST = ("bugfix", "security", "incident")


def std_drafts(R, rules, tasks=None):
    """[{name, title, src, chain, gp, P}] for role map R (pipeline._role_agents) and rule lines. Unmatched role ->
    general-purpose and the title goes into gp. ⚠Never drop a stage; optional stages stay out of P (chain only).
    tasks = {stage title: instruction} (the «Stage catalog»): the fallback for a non-recommended stage with no task here."""
    out = []
    for key, title, src, stages in STD:
        chain, gp, st = [], [], []
        for t, role, opt, fail, task in stages:
            chain.append({"title": t, "role": role, "opt": opt})
            if opt:
                continue
            keys = _ROLE_KEYS[role]
            if role == "B" and key in _FIX_FIRST:
                keys = ("fix", "build")
            elif role in ("M", "P") and key in _FIX_FIRST:
                keys = keys + ("fix",)   # a *-bugfix agent reproduces and finds the cause itself
            agent = next((R[k] for k in keys if R.get(k)), None)
            if agent is None:
                agent = "general-purpose"
                gp.append(t)
            s = {"title": t, "agent": agent}
            if role == "C":
                s["model"] = "sonnet"
            task = task or (tasks or {}).get(t)
            if task and t not in _REC:   # recommended titles get the runner's DEFAULT_TASKS; a task here would be sent twice
                s["task"] = task[:300]
            if fail:
                s["onFail"] = {"goto": fail[0], "max": fail[1]}
            st.append(s)
        P = {"v": 1, "name": key, "title": title, "rules": "\n".join(rules)}
        if key == "bugfix":
            P["catch"] = "person"   # a person found the defect: Harness «Found by a person first» counts its runs
        P.update(defaults={"model": "inherit", "retry": 0}, stages=st)
        out.append({"name": key, "title": title, "src": src, "chain": chain, "gp": gp, "P": P})
    return out
