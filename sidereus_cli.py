#!/usr/bin/env python3
"""Sidereus launcher: start [--port N] [--open] [--demo] [--install-service] | stop [--port N] | status  (stdlib only, Python 3.9).
Run as `python3 -m sidereus ...` (sidereus/__main__.py) or `python3 sidereus_cli.py ...`.

Port: --port N > env SIDEREUS_PORT > config `port` > 8799 (mailbox_config.port()). `start --port N` saves N to the config
once the viewer answers (`--install-service` saves it first: the service reads the config).

start   first run copies config.example.json -> config.local.json (never overwrites), then runs
        chat_server.py --no-open detached, records DATA_DIR/sidereus.pid and waits for /api/state.
        Opens a browser tab only with --open.
        --demo runs chat_server.py --demo in the foreground (port --port or 18799); no config, no pid record.
stop    stops only the pid this launcher recorded, and only while that pid is alive and its port answers.
        A viewer owned by launchd/schtasks (on that port) is left alone.
status  prints what it sees; writes nothing.
doctor  one OK/FAIL line per setup check (Python, git, claude, hooks, viewer; Windows interpreter); exit 1 on a FAIL.
setup-claude [--mailbox-mcp DIR]
        prints the `claude mcp add` lines and the hooks JSON block with this clone's real paths; writes nothing.
        --write shows the MCP command and a settings.json diff, asks, then backs up, merges hooks and registers MCP.
"""
import getpass
import json
import os
import plistlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE_DIR)
import mailbox_config  # noqa: E402

# Same rule as sidereus/config.py: assets (web/, hooks/, mcp/, plugin/) sit in sidereus/_bundle when pipx/uv installed.
ASSET_DIR = mailbox_config.asset_dir(CODE_DIR)
IS_CLONE = ASSET_DIR == CODE_DIR


def utf8_stdio(streams=None):
    """Re-encode non-UTF-8 stdio as UTF-8, keeping each stream's error mode.
    ⚠Windows pipes and redirects default to the ANSI code page (cp949 cannot encode the em dash in setup-claude)."""
    for s in streams or (sys.stdout, sys.stderr):
        try:
            if (getattr(s, "encoding", "") or "").lower().replace("-", "") != "utf8":
                s.reconfigure(encoding="utf-8", errors=s.errors)
        except Exception:
            pass


utf8_stdio()   # module level: `python -m sidereus` reaches main() through an import, not __main__

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
DEFAULT_PORT = mailbox_config.DEFAULT_PORT
DEMO_PORT = 18799
WIN_TASK = "Sidereus"
WIN_SPAWN_FLAGS = 0x08000000 | 0x00000200   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP (hidden console children inherit)
START_WAIT_S = 20.0           # ★first /api/state on a fresh data dir measured up to 6.5 s
BUSY = -1                    # answering(): connected but no reply in time = a live server that is busy
STOP_WAIT_S = 5.0
_sleep = time.sleep          # tests replace these module attributes
_now = time.time
_Popen = subprocess.Popen
_urlopen = urllib.request.urlopen
_open_tab = webbrowser.open
_IDENT = {}                  # port -> X-Sidereus-Instance of the last 200 answer ("" = header absent)


def _run_fg(argv, env=None):
    """subprocess.call that also forwards SIGTERM: without it a killed launcher leaves the server running."""
    with subprocess.Popen(argv, env=env) as p:
        old = signal.signal(signal.SIGTERM, lambda sig, frm: p.terminate())
        try:
            rc = p.wait()
            return 128 - rc if rc < 0 else rc    # signal-killed child: shell convention 128+signum (SIGTERM -> 143)
        except BaseException:
            p.kill()
            raise
        finally:
            signal.signal(signal.SIGTERM, old)


_call = _run_fg
_home = os.path.expanduser


# key -> (Korean, English); Korean only when the locale says ko (see lang()).
MSG = {
    "running_on": ("이미 %d 포트에서 실행 중입니다 — 먼저 `python3 -m sidereus stop` 후 다시 설치하세요.",
                   "Already running on port %d — run `python3 -m sidereus stop` first, then install again."),
    "svc_exists": ("서비스가 이미 설치되어 있습니다: %s", "Service already installed: %s"),
    "svc_mac": ("launchd 서비스 설치: %s (bootstrap %s)", "launchd service installed: %s (bootstrap %s)"),
    "failed_rc": ("실패 rc=%s", "failed rc=%s"),
    "schtasks_fail": ("schtasks 작업 생성 실패 (rc=%s)", "schtasks task creation failed (rc=%s)"),
    "svc_win": ("로그온 작업 '%s' 을 만들었습니다.", "Created logon task '%s'."),
    "svc_none": ("이 플랫폼은 서비스 설치를 지원하지 않습니다 — `python3 -m sidereus start` 로 실행하세요.",
                 "Service install is not supported on this platform — use `python3 -m sidereus start`."),
    "answer": ("응답 %d", "answered %d"),
    "port_unsaved": ("설정 파일을 읽지 못해 포트를 저장하지 않았습니다 — %s", "Config file unreadable, port not saved — %s"),
    "no_answer_yet": ("아직 응답 없음", "no answer yet"),
    "first_run": ("첫 실행: 설정 파일을 만들었습니다 — %s", "First run: created the config file — %s"),
    "already": ("이미 실행 중입니다 — %s", "Already running — %s"),
    "waiting": ("기동 중인 프로세스(pid %d)를 기다립니다...", "Waiting for the starting process (pid %d)..."),
    "started": ("시작했습니다 (pid %d) — 로그: %s", "Started (pid %d) — log: %s"),
    "timeout": ("%d초 안에 응답이 없습니다 — viewer.err 를 확인하세요.",
                "No answer within %d seconds — check viewer.err."),
    "up": ("실행 중 — %s", "Running — %s"),
    "busy": ("포트가 열려 있지만 응답이 늦습니다(바쁨) — 잠시 뒤 다시 확인하세요: %s",
             "The port is open but slow to answer (busy) — check again shortly: %s"),
    "st_busy": ("응답 지연(바쁨)", "slow answer (busy)"),
    "svc_owned": ("서비스(%s)가 관리 중이라 멈추지 않습니다 — 서비스 도구로 멈추세요.",
                  "Managed by a service (%s), not stopping it — stop it with the service tool."),
    "stop_other": ("%d 포트의 Sidereus 는 이 데이터 폴더에서 띄운 것이 아니거나 `--demo` 입니다 — 띄운 터미널에서 Ctrl+C 로, 또는 그 데이터 폴더에서 멈추세요.",
                   "The Sidereus on port %d was not started from this data dir, or is a `--demo` — stop it with Ctrl+C in its own terminal, or from that data dir."),
    "no_pid": ("실행 기록(sidereus.pid)이 없습니다 — 할 일이 없습니다.", "No run record (sidereus.pid) — nothing to do."),
    "gone": ("기록된 프로세스(pid %d)는 이미 멈췄습니다 — 기록을 지웠습니다.",
             "The recorded process (pid %d) already stopped — record removed."),
    "stopped": ("멈췄습니다 (pid %d).", "Stopped (pid %d)."),
    "not_stopped": ("pid %d 가 아직 멈추지 않았습니다 — 기록을 남겨 둡니다. 잠시 뒤 다시 `stop` 하세요.",
                    "pid %d has not stopped yet — record kept. Run `stop` again shortly."),
    "st_url": ("http://127.0.0.1:%d/api/state  %s", "http://127.0.0.1:%d/api/state  %s"),
    "st_none": ("응답 없음", "no answer"),
    "st_pid": ("pid: %s", "pid: %s"),
    "st_norec": ("기록 없음", "no record"),
    "st_cfg": ("설정: %s%s", "config: %s%s"),
    "st_missing": (" (없음 — start 가 만듭니다)", " (missing — `start` creates it)"),
    "st_svc": ("서비스: %s", "service: %s"),
    "st_inst": ("설치됨", "installed"),
    "st_inst_port": ("설치됨 (포트 %d)", "installed (port %d)"),
    "st_noinst": ("없음", "none"),
    "foreign": ("%d 포트를 Sidereus 가 아닌 다른 프로그램이 쓰고 있습니다 (응답 %d) — 다른 포트를 쓰세요: --port N",
                "Port %d is in use by something that isn't Sidereus (answered %d) — pick another: --port N"),
    "other_sidereus": ("%d 포트는 다른 Sidereus(다른 데이터 폴더) 또는 다른 프로그램이 쓰고 있습니다 — 다른 포트를 쓰세요: --port N",
                    "Port %d is taken by another Sidereus (different data dir) or another app — pick another: --port N"),
    "bad_port": ("--port 에는 1024–65535 사이의 숫자가 필요합니다.", "--port needs a number in 1024–65535."),
    "st_dead": (" (실행 중 아님)", " (not running)"),
    "st_unowned": ("%d 포트에 무언가 응답합니다 (실행 기록 없음)", "something answers on %d (no run record)"),
    "usage": ("사용법: python3 -m sidereus start [--port N] [--open] [--demo] [--install-service] | stop [--port N] | status [--port N]"
              " | setup-claude [--mailbox-mcp DIR] [--write [--yes]] | doctor [--port N]",
              "usage: python3 -m sidereus start [--port N] [--open] [--demo] [--install-service] | stop [--port N] | status [--port N]"
              " | setup-claude [--mailbox-mcp DIR] [--write [--yes]] | doctor [--port N]"),
    "dr_line": ("%-4s  %s — %s", "%-4s  %s — %s"),
    "dr_fix": (" — 해결: %s", " — fix: %s"),
    "dr_notfound": ("찾지 못함", "not found"),
    "dr_python": ("Python 3.9 이상", "Python 3.9+"),
    "dr_python_fix": ("Python 3.9 이상을 설치하세요", "install Python 3.9 or newer"),
    "dr_git": ("PATH 의 git", "git on PATH"),
    "dr_git_fix": ("git 을 설치하고 PATH 에 넣으세요", "install git and put it on PATH"),
    "dr_claude": ("PATH 의 claude", "claude on PATH"),
    "dr_claude_fix": ("Claude Code 를 설치하거나 터미널을 다시 여세요", "install Claude Code or reopen the terminal"),
    "dr_hooks": ("훅 연결", "hooks connected"),
    "dr_hooks_plugin": ("플러그인 설치됨", "plugin installed"),
    "dr_hooks_manual": ("%s 에 모두 있음", "all present in %s"),
    "dr_hooks_none": ("플러그인 없음, %s 에 빠진 훅 있음", "no plugin, hooks missing from %s"),
    "dr_hooks_fix": ("Claude Code 에서 /plugin install sidereus@sidereus 또는 python3 -m sidereus setup-claude --write",
                     "/plugin install sidereus@sidereus in Claude Code, or python3 -m sidereus setup-claude --write"),
    "dr_viewer": ("뷰어 응답", "viewer answering"),
    "dr_viewer_other": ("Sidereus 가 아닌 응답 %d", "non-Sidereus answer %d"),
    "dr_viewer_fix": ("python3 -m sidereus start", "python3 -m sidereus start"),
    "dr_winpy": ("SIDEREUS_PYTHON", "SIDEREUS_PYTHON"),
    "dr_unset": ("설정 안 됨", "not set"),
    "dr_nofile": ("%s (파일도 PATH 의 명령도 아님)", "%s (not a file or a command on PATH)"),
    "dr_alias_unused": ("%s (SIDEREUS_PYTHON 이 먼저 쓰여 문제없음)", "%s (unused: SIDEREUS_PYTHON is used first)"),
    "dr_winpy_fix": ("python.exe 전체 경로로 설정하세요: setx SIDEREUS_PYTHON C:\\...\\python.exe",
                     "set it to the full python.exe path: setx SIDEREUS_PYTHON C:\\...\\python.exe"),
    "dr_alias": ("python3 가 스토어 별칭이 아님", "python3 is not the Store alias"),
    "dr_alias_fix": ("설정 › 앱 실행 별칭에서 python3 를 끄세요", "turn off python3 in Settings > App execution aliases"),
    "setup_mcp": ("# 1) MCP 등록 — 터미널에서 실행하세요", "# 1) Register the MCP servers — run these in a terminal"),
    "setup_nombx": ("# mailbox-mcp 는 별도 패키지입니다 — 경로를 --mailbox-mcp DIR 로 주면 아래 줄이 채워집니다",
                    "# mailbox-mcp is a separate package — pass --mailbox-mcp DIR to fill in the line below"),
    "setup_hooks": ("# 2) ~/.claude/settings.json 의 \"hooks\" 에 합쳐 넣으세요 (이 명령은 아무 파일도 쓰지 않습니다)",
                    "# 2) Merge into \"hooks\" in ~/.claude/settings.json (this command writes no file)"),
    "w_mcp_run": ("MCP 등록 — 실행할 명령:\n  %s", "MCP registration — will run:\n  %s"),
    "w_mcp_have": ("MCP: sidereus 가 이미 등록되어 있습니다 — 건너뜁니다.", "MCP: sidereus is already registered — skipping."),
    "w_no_claude": ("MCP: `claude` 를 PATH 에서 찾지 못했습니다 — 터미널을 다시 연 뒤 다시 실행하거나 직접 실행하세요:\n  %s",
                    "MCP: `claude` is not on PATH — reopen the terminal and rerun, or run it yourself:\n  %s"),
    "w_plugin": ("훅: Sidereus 플러그인이 설치되어 있어 훅을 넣지 않습니다(두 번 실행됨). MCP 만 등록합니다.",
                 "Hooks: the Sidereus plugin is installed, so no hooks are added (they would run twice). Only MCP is registered."),
    "w_hooks_have": ("훅: %s 에 이미 모두 들어 있습니다.", "Hooks: already all present in %s."),
    "w_diff": ("훅: %s 변경 내용:", "Hooks: changes to %s:"),
    "w_symlink": ("%s 는 심볼릭 링크입니다 — 쓰지 않습니다. 실제 파일에 직접 합치세요.",
                  "%s is a symlink — not writing it. Merge into the real file by hand."),
    "w_invalid": ("%s 를 JSON 객체로 읽지 못했습니다 — 쓰지 않습니다. 파일을 고친 뒤 다시 실행하세요.",
                  "%s is not a valid JSON object — not writing it. Fix the file and rerun."),
    "w_nothing": ("바꿀 것이 없습니다.", "Nothing to change."),
    "w_ask": ("적용할까요? [y/N] ", "Apply? [y/N] "),
    "w_notty": ("터미널이 아니라 묻지 못했습니다 — 아무것도 쓰지 않았습니다. 적용하려면 --yes 를 붙이세요.",
                "Not a terminal, cannot ask — nothing written. Add --yes to apply."),
    "w_cancel": ("취소했습니다 — 아무것도 쓰지 않았습니다.", "Cancelled — nothing written."),
    "w_backup": ("백업: %s", "Backup: %s"),
    "w_wrote": ("썼습니다: %s", "Wrote: %s"),
    "svc_pkg": ("--install-service 는 git clone 에서만 됩니다 — pipx/uv 가 쓰는 Python 이 바뀌면 설치 경로도 바뀝니다. "
                "clone 을 쓰거나, 로그인할 때 `sidereus start` 를 실행하세요.",
                "--install-service works only from a git clone — the pipx/uv install path changes when its Python changes. "
                "Use a clone, or run `sidereus start` at login."),
    "setup_pkg": ("# 먼저 GitHub 의 Sidereus 플러그인을 권합니다 (Claude Code: /plugin marketplace add bugsterran/sidereus) — 아래는 수동 설정입니다",
                  "# Prefer the Sidereus plugin from GitHub first (Claude Code: /plugin marketplace add bugsterran/sidereus) — manual setup below"),
    "w_mcp_ok": ("MCP: sidereus 를 등록했습니다.", "MCP: sidereus registered."),
    "w_mcp_fail": ("MCP 등록 실패 (rc=%s) — 직접 실행하세요:\n  %s", "MCP registration failed (rc=%s) — run it yourself:\n  %s"),
}


def lang():
    """'ko' when the first set of LC_ALL / LC_MESSAGES / LANG starts with 'ko', else 'en'."""
    for k in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(k)
        if v:
            return "ko" if v.lower().startswith("ko") else "en"
    return "en"


def t(key, *args):
    s = MSG[key][0 if lang() == "ko" else 1]
    return s % args if args else s


def _run(argv):
    """Run a service tool; returncode, or None when the tool is missing."""
    try:
        return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=20).returncode
    except (OSError, subprocess.SubprocessError):
        return None


def data_dir():
    return mailbox_config.data_dir()


def pid_path():
    return os.path.join(data_dir(), "sidereus.pid")


def pid_alive(pid):
    # ⚠os.kill(pid, 0) on Windows is TerminateProcess, not a probe — never use it there.
    try:
        from sidereus import config as _cfg
        fn = getattr(_cfg, "pid_alive", None)
    except Exception:
        fn = None
    if fn is not None:
        return bool(fn(pid))
    if IS_WIN:
        return False         # no safe probe without sidereus.config.pid_alive: treat as gone, never kill
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def port_bound(port):
    """True when something holds 127.0.0.1:port (our probe bind fails)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", int(port)))
        return False
    except OSError:
        return True          # in use, or reserved/denied (WSAEACCES): not free either way
    finally:
        s.close()


def answering(port):
    """HTTP status of /api/state on port, BUSY on timeout, 0 when nothing answers. ⚠Only 200 means Sidereus (is_sidereus)."""
    try:
        r = _urlopen("http://127.0.0.1:%d/api/state" % int(port), timeout=2)
        try:
            _IDENT[int(port)] = (getattr(r, "headers", None) or {}).get("X-Sidereus-Instance") or ""
            return int(getattr(r, "status", 0) or r.getcode() or 0)
        finally:
            r.close()
    except Exception as e:
        # ⚠A timeout is not «down»: /api/state can take >2 s (measured up to 6.5 s); treating it as 0 dropped live records.
        if isinstance(e, socket.timeout) or isinstance(getattr(e, "reason", None), socket.timeout):
            # ⚠Windows retries SYN to a closed localhost port for ~2 s, so a free port also times out; only a bound one is BUSY.
            if IS_WIN and not port_bound(port):
                return 0
            return BUSY
        return int(getattr(e, "code", 0) or 0)


def is_sidereus(code):
    # ⚠Any other status is a foreign server on the port (a plain http.server answers 404): never «already running».
    return code == 200


def is_ours(port):
    """The Sidereus answering on port serves this data dir. ⚠A 200 alone was taken as «already running» even when
    another clone/data dir owned the port. No header (older viewer): ours only if our recorded live pid holds the port."""
    ident = _IDENT.get(int(port), "")
    if ident:
        return ident == mailbox_config.instance_id(data_dir())
    rec = read_pid()
    return bool(rec and rec["port"] == int(port) and pid_alive(rec["pid"]))


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def default_id():
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    user = re.sub(r"[^A-Za-z0-9._-]", "", user or "") or "me"
    return user + "-sidereus"


def ensure_config():
    """Create config.local.json from the example on first run. True only when this call created it."""
    path = mailbox_config.config_path()
    if os.path.exists(path):
        return False
    with open(os.path.join(ASSET_DIR, "config.example.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    # The example's header says «copy to config.local.json»; optional saver-hook keys equal to the defaults add nothing.
    cfg.pop("_comment", None)
    for k in ("saver_view_path", "saver_hook_dir"):
        if cfg.get(k) == mailbox_config.DEFAULTS.get(k):
            cfg.pop(k, None)
    cfg.pop("_saver_view_comment", None)
    me = default_id()
    cfg.setdefault("self", {})
    cfg["self"]["ids"] = [me]
    cfg["self"]["aliases"] = [me]
    if os.path.exists(path):     # ⚠never overwrite a config another process wrote meanwhile
        return False
    _atomic_write(path, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    mailbox_config.load(reload=True)
    return True


def read_pid():
    try:
        with open(pid_path(), encoding="utf-8") as f:
            d = json.load(f)
        return {"pid": int(d["pid"]), "port": int(d.get("port") or mailbox_config.port()), "started": d.get("started")}
    except Exception:
        return None


def _drop_pid():
    try:
        os.remove(pid_path())
    except OSError:
        pass


def configured_port():
    mailbox_config.load(reload=True)
    return mailbox_config.port()


def save_port(port):
    """Write `port` into config.local.json, other keys untouched. ⚠A broken file is left alone (returns False)."""
    path = mailbox_config.config_path()
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {}
    except (OSError, ValueError):
        return False
    if not isinstance(cfg, dict):
        return False
    if cfg.get("port") != int(port):
        cfg["port"] = int(port)
        _atomic_write(path, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    mailbox_config.load(reload=True)
    return True


def server_argv(python, port, code=CODE_DIR):
    # ⚠--port only when the config does not already say it: the server reads the config itself, so a service
    #   built without the flag follows a later «Port» change after a restart (a baked-in flag would override it).
    argv = [python, os.path.join(code, "chat_server.py"), "--no-open"]
    if int(port) != configured_port():
        argv += ["--port", str(int(port))]
    return argv


def spawn(port):
    """Start chat_server.py detached; stdout/stderr append to DATA_DIR viewer.log/viewer.err."""
    d = data_dir()
    os.makedirs(d, exist_ok=True)
    out = open(os.path.join(d, "viewer.log"), "a", encoding="utf-8")
    err = open(os.path.join(d, "viewer.err"), "a", encoding="utf-8")
    kw = {"cwd": CODE_DIR, "stdin": subprocess.DEVNULL, "stdout": out, "stderr": err, "close_fds": True}
    if IS_WIN:
        # ⚠Not DETACHED_PROCESS: a console-less server makes every console child (git, claude) open its own window per poll.
        kw["creationflags"] = WIN_SPAWN_FLAGS
        kw["env"] = dict(os.environ, PYTHONUTF8="1")   # redirected stdio would use the ANSI code page and fail on Korean
    else:
        kw["start_new_session"] = True
    try:
        p = _Popen(server_argv(sys.executable, port), **kw)
    finally:
        out.close()
        err.close()
    _atomic_write(pid_path(), json.dumps({"pid": p.pid, "port": int(port), "started": int(_now())}) + "\n")
    return p.pid


def wait_up(port, limit=START_WAIT_S):
    end = _now() + limit
    while True:
        code = answering(port)
        if code and code != BUSY:
            return code      # 200 = up; another status = a foreign server, stop waiting
        if _now() >= end:
            return code      # 0 = nothing, BUSY = listening but still not replying
        _sleep(0.5)


# ---- service (launchd / schtasks) ----

def mac_label():
    mailbox_config.load(reload=True)
    return mailbox_config.launchd_label("viewer")


def mac_plist_path(label):
    return os.path.join(_home("~"), "Library", "LaunchAgents", label + ".plist")


def build_plist(label, port, data, code=CODE_DIR, python="/usr/bin/python3"):
    """launchd agent text for the viewer (pure)."""
    return plistlib.dumps({
        "Label": label,
        "ProgramArguments": server_argv(python, port, code),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": os.path.join(data, "viewer.log"),
        "StandardErrorPath": os.path.join(data, "viewer.err"),
        "WorkingDirectory": code,
    }).decode("utf-8")


def pythonw(python=None):
    python = python or sys.executable
    d, b = os.path.split(python)
    if b.lower() == "python.exe":
        cand = os.path.join(d, "pythonw.exe")
        if os.path.exists(cand):
            return cand
    return python


def schtasks_argv(pyw, port, code=CODE_DIR):
    """schtasks /Create argv for a logon task (pure)."""
    tr = '"%s" "%s" --no-open' % (pyw, os.path.join(code, "chat_server.py"))
    if int(port) != configured_port():
        tr += " --port %d" % int(port)
    return ["schtasks", "/Create", "/SC", "ONLOGON", "/TN", WIN_TASK, "/TR", tr]


def service_installed():
    if IS_MAC:
        return os.path.exists(mac_plist_path(mac_label()))
    if IS_WIN:
        return _run(["schtasks", "/Query", "/TN", WIN_TASK]) == 0
    return False


def _run_out(argv):
    """Run a read-only service query; its stdout text, or "" on failure."""
    try:
        r = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.decode("utf-8", "replace").replace("\x00", "") if r.returncode == 0 else ""


def service_port():
    """Port the installed service serves, None when not installed or unreadable.
    No --port in its argv = it follows the config (server_argv / schtasks_argv omit the flag then)."""
    args = None
    if IS_MAC:
        try:
            with open(mac_plist_path(mac_label()), "rb") as f:
                args = " ".join(str(a) for a in plistlib.load(f).get("ProgramArguments") or [])
        except Exception:
            return None
    elif IS_WIN:
        args = _run_out(["schtasks", "/Query", "/TN", WIN_TASK, "/XML"])
    if not args:
        return None
    m = re.search(r"--port\s+(\d+)", args)
    return int(m.group(1)) if m else configured_port()


def svc_owns(port):
    # ⚠Installed alone is not ownership: a --demo or second instance on another port is not the service's.
    if not service_installed():
        return False
    sp = service_port()
    return sp is None or sp == int(port)


def install_service(port):
    code = answering(port)
    if code == BUSY:
        print(t("busy", "http://127.0.0.1:%d/" % port))
        return 1
    if code:
        print(t("running_on", port) if is_sidereus(code) else t("foreign", port, code))
        return 1
    if IS_MAC:
        label = mac_label()
        path = mac_plist_path(label)
        if os.path.exists(path):
            print(t("svc_exists", path))
            return 0
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _atomic_write(path, build_plist(label, port, data_dir()))
        rc = _run(["launchctl", "bootstrap", "gui/%d" % os.getuid(), path])
        print(t("svc_mac", path, "ok" if rc == 0 else t("failed_rc", rc)))
    elif IS_WIN:
        rc = _run(schtasks_argv(pythonw(), port))
        if rc != 0:
            print(t("schtasks_fail", rc))
            return 1
        _run(["schtasks", "/Run", "/TN", WIN_TASK])
        print(t("svc_win", WIN_TASK))
    else:
        print(t("svc_none"))
        return 2
    code = wait_up(port)
    print("http://127.0.0.1:%d  %s" % (port, t("answer", code) if code else t("no_answer_yet")))
    return 0 if is_sidereus(code) else 1


# ---- commands ----

def cmd_demo(port=None, open_tab=False):
    # Synthetic world in the foreground: touches neither the config nor sidereus.pid (sidereus/demo.py reads nothing real).
    argv = [sys.executable, os.path.join(CODE_DIR, "chat_server.py"), "--demo", "--port", str(port or DEMO_PORT)]
    # ⚠ sidereus/config.py creates DATA_DIR at import: point it at a throwaway dir so the demo leaves no ~/.mailbox-mcp.
    tmp = tempfile.mkdtemp(prefix="sidereus-demo-")
    env = {k: v for k, v in os.environ.items() if k != "MAILBOX_CONFIG"}
    env["MAILBOX_DIR"] = tmp
    try:
        return _call(argv + ([] if open_tab else ["--no-open"]), env=env)
    except KeyboardInterrupt:    # Ctrl-C is the normal way to end the demo
        return 130
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_start(port=None, install=False, open_tab=False):
    if install and not IS_CLONE:
        print(t("svc_pkg"))   # ⚠the venv path changes when pipx/uv's Python changes, so a service would break; writes nothing
        return 2
    created = ensure_config()
    if created:
        print(t("first_run", mailbox_config.config_path()))
    explicit = port is not None
    if not explicit:
        port = configured_port()
    if install:
        if explicit and not save_port(port):   # the service reads the config, so save before building it
            print(t("port_unsaved", mailbox_config.config_path()))
        return install_service(port)
    url = "http://127.0.0.1:%d/" % port
    code = answering(port)
    if code and code != BUSY and not is_sidereus(code):
        print(t("foreign", port, code))
        return 1
    if code == 200 and not is_ours(port):
        print(t("other_sidereus", port))
        return 1
    if code == 200:
        print(t("already", url))
        _keep_port(port, explicit)
        if open_tab:
            _open_tab(url)
        return 0
    rec = read_pid()
    if rec and rec["port"] == port and pid_alive(rec["pid"]):
        # ⚠single spawn guard: a recorded live pid is still booting — wait for it, do not start a second one.
        print(t("waiting", rec["pid"]))
    elif code == BUSY:
        pass                 # something already holds the port: a second server would only fail to bind
    else:
        pid = spawn(port)
        print(t("started", pid, os.path.join(data_dir(), "viewer.err")))
    code = wait_up(port)
    if code and code != BUSY and not is_sidereus(code):
        print(t("foreign", port, code))
        return 1
    if code == BUSY:
        print(t("busy", url))
        return 1
    if code == 200 and not is_ours(port):
        print(t("other_sidereus", port))
        return 1
    if not code:
        print(t("timeout", int(START_WAIT_S)))
        return 1
    print(t("up", url))
    _keep_port(port, explicit)
    if open_tab:
        _open_tab(url)
    return 0


def _keep_port(port, explicit):
    # ⚠Saved only once the viewer answers: a port that failed to start must not become the next default.
    if explicit and not save_port(port):
        print(t("port_unsaved", mailbox_config.config_path()))


def cmd_stop(port=None):
    rec = read_pid()
    if port is None:
        port = rec["port"] if rec else configured_port()
    if svc_owns(port):
        print(t("svc_owned", "launchd" if IS_MAC else "schtasks"))
        return 0
    if not rec or rec["port"] != port:
        # No handle on that process: never kill by port, only point at whoever started it.
        print(t("stop_other", port) if is_sidereus(answering(port)) else t("no_pid"))
        return 0
    code = answering(rec["port"])
    # BUSY + live pid = our server, just slow: still ours to stop, never «already stopped».
    if not (pid_alive(rec["pid"]) and (is_sidereus(code) or code == BUSY)):
        _drop_pid()
        print(t("gone", rec["pid"]))
        return 0
    # ⚠On Windows this is TerminateProcess (no cleanup) — safe only behind the pid + answering guard above.
    os.kill(rec["pid"], signal.SIGTERM)
    end = _now() + STOP_WAIT_S
    code = answering(rec["port"])
    while code and _now() < end:
        _sleep(0.3)
        code = answering(rec["port"])
    if code and pid_alive(rec["pid"]):
        print(t("not_stopped", rec["pid"]))     # keep the record: it is still the only handle on that process
        return 1
    _drop_pid()
    print(t("stopped", rec["pid"]))
    return 0


def cmd_status(port=None):
    rec = read_pid()
    if port is None:     # no --port: the recorded port wins, the default only when there is no record
        port = rec["port"] if rec else configured_port()
    code = answering(port)
    svc = service_installed()
    sport = service_port() if svc else None
    owns = svc and (sport is None or sport == port)
    print(t("st_url", port, t("st_busy") if code == BUSY else (code or t("st_none"))))
    if code and code != BUSY and not is_sidereus(code):
        print(t("foreign", port, code))
    elif code and not rec and not owns:
        print(t("st_unowned", port))     # not started from this data dir: don't present it as yours
    if rec:
        print(t("st_pid", "%d (port %d)%s" % (rec["pid"], rec["port"], "" if pid_alive(rec["pid"]) else t("st_dead"))))
    else:
        print(t("st_pid", t("st_norec")))
    print(t("st_cfg", os.path.normpath(mailbox_config.config_path()), "" if os.path.exists(mailbox_config.config_path()) else t("st_missing")))
    print(t("st_svc", (t("st_inst_port", sport) if sport else t("st_inst")) if svc else t("st_noinst")))
    return 0


def _shq(p):
    """Quote a path for the printed shell line only when needed."""
    if IS_WIN:
        return '"%s"' % p    # ⚠always: cmd metacharacters (& ( ) ^ | < > % !) break unquoted paths; `"` cannot occur in one
    return p if re.match(r"^[\w@%+=:,./-]+$", p) else "'" + p.replace("'", "'\\''") + "'"


_PLUGIN_CMD = re.compile(r'^sh "\$\{CLAUDE_PLUGIN_ROOT\}/hooks/pyrun\.sh" "\$\{CLAUDE_PLUGIN_ROOT\}/hooks/([\w.-]+\.py)"$')


def setup_hooks(python, code=ASSET_DIR):
    """The plugin's hook set (plugin/hooks/hooks.json, built by scripts/build_plugin.py) with this clone's paths.
    ⚠Derived, not hand-copied: a hand-kept list here missed mailbox_wake and the pipeline hooks."""
    with open(os.path.join(code, "plugin", "hooks", "hooks.json"), encoding="utf-8") as f:
        src = json.load(f)

    def fix(h):
        h = dict(h)
        m = _PLUGIN_CMD.match(h.get("command") or "")
        if m:
            h["command"] = "%s %s" % (_shq(python), _shq(os.path.join(code, "hooks", m.group(1))))
        return h
    return {"hooks": {ev: [dict(g, hooks=[fix(h) for h in g.get("hooks", [])]) for g in groups]
                      for ev, groups in src.get("hooks", {}).items()}}


def setup_claude_text(python, code=ASSET_DIR, mailbox_mcp=None):
    """Text of `setup-claude` (pure, prints only). Writing is `--write` (cmd_setup_write): confirm + backup first."""
    hooks = setup_hooks(python, code)
    lines = [t("setup_mcp"),
             "claude mcp add --scope user sidereus -- %s %s" % (_shq(python), _shq(os.path.join(code, "mcp", "sidereus_mcp.py")))]
    if mailbox_mcp:
        lines.append("claude mcp add --scope user mailbox -- uv --directory %s run mailbox-mcp" % _shq(mailbox_mcp))
    else:
        lines += [t("setup_nombx"), "claude mcp add --scope user mailbox -- uv --directory <path-to-mailbox-mcp> run mailbox-mcp"]
    lines += ["", t("setup_hooks"), json.dumps(hooks, indent=2)]
    return "\n".join(lines)


def _probe_exe(python):
    try:
        r = subprocess.run([python, "-c", "import sys; print(sys.executable)"], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def setup_python(exe=None, probe=_probe_exe, doc="/usr/bin/python3"):
    """The interpreter path to print: the documented /usr/bin/python3 when it runs this same interpreter (macOS only).
    ⚠On macOS sys.executable is the CommandLineTools/Xcode path behind the /usr/bin shim; that path moves with xcode-select."""
    exe = exe if exe is not None else (sys.executable or "python3")
    if not IS_MAC or exe == doc or not os.path.exists(doc):
        return exe
    real = probe(doc)
    try:
        return doc if real and os.path.samefile(real, exe) else exe
    except OSError:
        return exe


_which = shutil.which      # tests replace these module attributes
_isatty = lambda: sys.stdin.isatty()   # noqa: E731
_input = input
_sub_run = subprocess.run


def claude_home():
    from sidereus import config as _scfg    # lazy: the launcher must not pull the viewer package at import
    return _scfg.claude_home()


def plugin_installed(home):
    """True when an enabled `sidereus@...` plugin with an existing installPath is in this account's registry."""
    def load(p):
        try:
            with open(p, encoding="utf-8") as f:
                v = json.load(f)
            return v if isinstance(v, dict) else {}
        except (OSError, ValueError):
            return {}
    reg = load(os.path.join(home, "plugins", "installed_plugins.json")).get("plugins")
    en = {}
    for name in ("settings.json", "settings.local.json"):
        e = load(os.path.join(home, name)).get("enabledPlugins")
        if isinstance(e, dict):
            en.update(e)
    for k, insts in (reg.items() if isinstance(reg, dict) else ()):
        if str(k).partition("@")[0] != "sidereus" or en.get(k, True) is False:   # missing key = enabled
            continue
        for inst in insts if isinstance(insts, list) else ():
            ip = inst.get("installPath") if isinstance(inst, dict) else None
            if isinstance(ip, str) and os.path.isdir(ip):
                return True
    return False


def merge_hooks(settings, hooks):
    """Copy of settings with every hook command of `hooks` not yet present under its event appended (exact command match)."""
    out = dict(settings)
    cur = out.get("hooks") if isinstance(out.get("hooks"), dict) else {}
    cur = dict(cur)
    for ev, groups in hooks.items():
        have = list(cur.get(ev)) if isinstance(cur.get(ev), list) else []
        seen = {h.get("command") for g in have if isinstance(g, dict)
                for h in (g.get("hooks") if isinstance(g.get("hooks"), list) else []) if isinstance(h, dict)}
        added = False
        for g in groups:
            new = [h for h in g.get("hooks", []) if h.get("command") not in seen]
            if new:
                have.append(dict(g, hooks=new))
                seen.update(h.get("command") for h in new)
                added = True
        if added:
            cur[ev] = have
    if cur != (settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}):
        out["hooks"] = cur
    return out


def _indent_of(text):
    """The file's JSON indent (first indented line), default 2; a tab stays a tab."""
    m = re.search(r"\n([ \t]+)\S", text)
    if not m:
        return 2
    ws = m.group(1)
    return "\t" if ws.startswith("\t") else len(ws)


def mcp_add_argv(claude, python, code=ASSET_DIR, win=None):
    """`claude mcp add` argv. ⚠name before -e: --env is variadic and would swallow the name. Windows gets UTF-8 stdio:
    a cp949 console crashed the server on a non-ASCII dash."""
    argv = [claude, "mcp", "add", "--scope", "user", "sidereus"]
    if IS_WIN if win is None else win:
        argv += ["-e", "PYTHONUTF8=1", "-e", "PYTHONIOENCODING=utf-8"]
    return argv + ["--", python, os.path.join(code, "mcp", "sidereus_mcp.py")]


def _argv_text(argv):
    return " ".join(_shq(a) for a in argv)


def _write_settings(path, text):
    """Atomic replace that keeps the original file mode."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cmd_setup_write(python, yes=False):
    """`setup-claude --write`: show the MCP command and the settings.json diff, confirm, back up, write, register."""
    import difflib
    home = claude_home()
    path = os.path.join(home, "settings.json")
    plugin = plugin_installed(home)
    old_text, obj = "", {}
    if os.path.islink(path):
        print(t("w_symlink", path))
        return 1
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8", newline="") as f:
                old_text = f.read()
            obj = json.loads(old_text) if old_text.strip() else {}
        except (OSError, ValueError):
            obj = None
        if not isinstance(obj, dict):
            print(t("w_invalid", path))
            return 1
    new_obj = obj if plugin else merge_hooks(obj, setup_hooks(python)["hooks"])
    new_text = old_text
    if new_obj != obj:
        nl = "\r\n" if "\r\n" in old_text else "\n"
        tail = nl if (old_text.endswith(("\n", "\r\n")) or not old_text) else ""
        new_text = json.dumps(new_obj, indent=_indent_of(old_text), ensure_ascii=False).replace("\n", nl) + tail
    claude = _which("claude")
    add = mcp_add_argv(claude or "claude", python)
    have_mcp = False
    if claude:
        try:
            have_mcp = _sub_run([claude, "mcp", "get", "sidereus"], stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            have_mcp = False
    if not claude:
        print(t("w_no_claude", _argv_text(add)))
    elif have_mcp:
        print(t("w_mcp_have"))
    else:
        print(t("w_mcp_run", _argv_text(add)))
    if plugin:
        print(t("w_plugin"))
    elif new_text == old_text:
        print(t("w_hooks_have", path))
    else:
        print(t("w_diff", path))
        sys.stdout.writelines(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True), path, path + " (new)"))
        print()
    run_mcp = bool(claude) and not have_mcp
    if new_text == old_text and not run_mcp:
        print(t("w_nothing"))
        return 0 if claude else 1
    if not yes:
        if not _isatty():
            print(t("w_notty"))
            return 1
        if _input(t("w_ask")).strip().lower() not in ("y", "yes"):
            print(t("w_cancel"))
            return 1
    if new_text != old_text:
        if os.path.exists(path):
            bak = "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S", time.localtime(_now())))
            shutil.copy2(path, bak)
            print(t("w_backup", bak))
        _write_settings(path, new_text)
        print(t("w_wrote", path))
    rc = 0 if claude else 1
    if run_mcp:
        try:
            r = _sub_run(add, stdin=subprocess.DEVNULL, timeout=60).returncode
        except (OSError, subprocess.SubprocessError):
            r = None
        if r == 0:
            print(t("w_mcp_ok"))
        else:
            print(t("w_mcp_fail", r, _argv_text(add)))
            rc = 1
    return rc


def cmd_setup_claude(rest):
    if "--write" in rest:
        return cmd_setup_write(setup_python(), "--yes" in rest)
    mbx = None
    if "--mailbox-mcp" in rest:
        try:
            mbx = os.path.abspath(os.path.expanduser(rest[rest.index("--mailbox-mcp") + 1]))
        except IndexError:
            print(t("usage"))
            return 2
        if not os.path.isdir(mbx):
            print(t("usage"))
            return 2
    if not IS_CLONE:
        print(t("setup_pkg"))
    print(setup_claude_text(setup_python(), ASSET_DIR, mbx))
    return 0


def _read_settings(home):
    try:
        with open(os.path.join(home, "settings.json"), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _hook_cmds(hooks):
    return [h.get("command") or "" for groups in (hooks.values() if isinstance(hooks, dict) else ())
            for g in (groups if isinstance(groups, list) else ()) if isinstance(g, dict)
            for h in (g.get("hooks") if isinstance(g.get("hooks"), list) else ()) if isinstance(h, dict)]


def missing_hook_scripts(settings, want):
    """Hook script file names of `want` that no settings.json hook command mentions.
    ⚠By basename, any path/interpreter: an exact-command match failed working setups whose hooks live elsewhere."""
    names = sorted({m.group(1) for c in _hook_cmds(want) for m in [re.search(r"([\w.-]+\.py)['\"]?$", c)] if m})
    have = _hook_cmds(settings.get("hooks") if isinstance(settings, dict) else None)
    return [n for n in names if not any(re.search(r"(^|[\\/'\"\s])" + re.escape(n) + r"(['\"\s]|$)", c) for c in have)]


def doctor_checks(port, home, python, win=None, env=None, version=None):
    """[(name, ok, detail, fix)] for `doctor`; reads only (PATH, settings.json, plugin registry, one GET on port)."""
    win = IS_WIN if win is None else win
    env = os.environ if env is None else env
    version = tuple(sys.version_info[:3]) if version is None else tuple(version)
    out = [(t("dr_python"), version >= (3, 9), ".".join(str(n) for n in version), t("dr_python_fix"))]
    for tool in ("git", "claude"):
        p = _which(tool)
        out.append((t("dr_" + tool), bool(p), p or t("dr_notfound"), t("dr_%s_fix" % tool)))
    spath = os.path.join(home, "settings.json")
    if plugin_installed(home):
        out.append((t("dr_hooks"), True, t("dr_hooks_plugin"), ""))
    else:
        miss = missing_hook_scripts(_read_settings(home), setup_hooks(python)["hooks"])
        ok = not miss
        out.append((t("dr_hooks"), ok, t("dr_hooks_manual", spath) if ok else
                    t("dr_hooks_none", spath) + " (" + ", ".join(miss) + ")", t("dr_hooks_fix")))
    code = answering(port)
    # ⚠BUSY = bound and slow (a cold /api/state took 6.5 s); telling the user to `start` again would be wrong.
    ok = is_sidereus(code) or code == BUSY
    detail = t("answer", code) if ok and code != BUSY else (t("st_busy") if code == BUSY else
                                                            (t("dr_viewer_other", code) if code else t("st_none")))
    out.append((t("dr_viewer"), ok, "http://127.0.0.1:%d — %s" % (int(port), detail), t("dr_viewer_fix")))
    if win:
        sp = env.get("SIDEREUS_PYTHON") or ""
        sp_ok = bool(sp) and (os.path.isfile(sp) or bool(_which(sp)))    # a command name (`py`) is the documented form
        out.append((t("dr_winpy"), sp_ok, (sp if sp_ok else t("dr_nofile", sp)) if sp else t("dr_unset"),
                    t("dr_winpy_fix")))
        p3 = _which("python3") or ""
        alias = "windowsapps" in p3.lower()     # ⚠the Store stub opens the Store instead of running a hook
        # pyrun.sh and .mcp.json use SIDEREUS_PYTHON first, so the alias only matters without it.
        out.append((t("dr_alias"), not alias or sp_ok, t("dr_alias_unused", p3) if alias and sp_ok
                    else (p3 or t("dr_notfound")), t("dr_alias_fix")))
    return out


def cmd_doctor(port=None):
    rows = doctor_checks(port or configured_port(), claude_home(), setup_python())
    for name, ok, detail, fix in rows:
        print(t("dr_line", "OK" if ok else "FAIL", name, detail) + ("" if ok else t("dr_fix", fix)))
    return 0 if all(r[1] for r in rows) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and (argv[0] == "help" or "--help" in argv or "-h" in argv):
        print(t("usage"))
        return 0
    if not argv or argv[0] not in ("start", "stop", "status", "setup-claude", "doctor"):
        print(t("usage"))
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "setup-claude":
        return cmd_setup_claude(rest)
    port = None
    if "--port" in rest:
        try:
            port = int(rest[rest.index("--port") + 1])
        except (IndexError, ValueError):
            port = 0
        if not 1024 <= port <= 65535:    # below 1024 needs root on POSIX
            print(t("bad_port"))
            return 2
    if cmd == "start" and "--demo" in rest:
        if "--install-service" in rest:
            print(t("usage"))
            return 2
        return cmd_demo(port, "--open" in rest)
    if cmd == "start":
        return cmd_start(port, "--install-service" in rest, "--open" in rest)
    if cmd == "stop":
        return cmd_stop(port)
    if cmd == "doctor":
        return cmd_doctor(port)
    return cmd_status(port)


if __name__ == "__main__":
    sys.exit(main())
