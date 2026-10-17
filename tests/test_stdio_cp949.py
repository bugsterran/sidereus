"""Windows code page simulation: stdio entry points must not die on a cp949 pipe (the em dash is not in cp949)."""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests._load import ROOT

PY = sys.executable


def _cp949():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp949")


class Cp949Test(unittest.TestCase):
    def test_simulated_stream_fails_without_fix(self):
        with self.assertRaises(UnicodeEncodeError):
            _cp949().write("—")

    def test_mcp_tools_list_over_cp949_pipe(self):
        # PYTHONIOENCODING=cp949 gives the child the same stdio a Korean Windows pipe has.
        tmp = tempfile.mkdtemp()
        try:
            env = dict(os.environ, PYTHONIOENCODING="cp949", HOME=tmp, USERPROFILE=tmp, MAILBOX_DIR=tmp,
                       SIDEREUS_PORT="9")
            msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
            r = subprocess.run([PY, os.path.join(ROOT, "mcp", "sidereus_mcp.py")], cwd=tmp, env=env, timeout=20,
                               input="".join(json.dumps(m) + "\n" for m in msgs).encode("utf-8"), capture_output=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        out = [json.loads(line) for line in r.stdout.decode("utf-8").splitlines()]
        self.assertEqual([o["id"] for o in out], [1, 2])
        self.assertIn("—", json.dumps(out[1]["result"]["tools"], ensure_ascii=False))

    def test_mcp_utf8_stdio(self):
        spec = importlib.util.spec_from_file_location("sidereus_mcp_cp", os.path.join(ROOT, "mcp", "sidereus_mcp.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        s = _cp949()
        m.utf8_stdio([s, io.StringIO()])     # a stream without reconfigure is skipped, not fatal
        s.write("—")
        s.flush()
        self.assertEqual(s.buffer.getvalue(), "—".encode("utf-8"))

    def test_cli_utf8_stdio_keeps_error_mode(self):
        spec = importlib.util.spec_from_file_location("sidereus_cli_cp", os.path.join(ROOT, "sidereus_cli.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        s = io.TextIOWrapper(io.BytesIO(), encoding="cp949", errors="backslashreplace")
        cli.utf8_stdio([s])
        self.assertEqual((s.encoding, s.errors), ("utf-8", "backslashreplace"))
        s.write("—")
        s.flush()
        self.assertEqual(s.buffer.getvalue(), "—".encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
