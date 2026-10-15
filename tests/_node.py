"""node_e(src, *args): argv for `node -e src args...` that keeps the source out of argv.

⚠Linux caps one argv string at MAX_ARG_STRLEN (128 KiB) -> «OSError: Argument list too long: 'node'» on CI; macOS has no such cap.
The source goes to a temp file; a short -e loader reads it, deletes it, drops its path from process.argv and runs it
with a global (indirect) eval in the same [eval] context, so require/module/import()/process.argv behave as with `node -e src`.
⚠Not vm.runInThisContext: it lacks a dynamic-import callback (ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING).
"""
import atexit
import os
import tempfile

ARG_MAX_SAFE = 100000

_LOADER = ("const __f = process.argv.splice(1, 1)[0], __fs = require('fs'), __s = __fs.readFileSync(__f, 'utf8');"
           " try { __fs.unlinkSync(__f); } catch (e) {}"
           " (0, eval)(__s);")
_LEFT = []


@atexit.register
def _cleanup():
    for p in _LEFT:
        try:
            os.unlink(p)
        except OSError:
            pass


def node_e(src, *args):
    if isinstance(src, bytes):
        src = src.decode("utf-8")
    fd, path = tempfile.mkstemp(prefix="node-e-", suffix=".js")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(src)
    _LEFT.append(path)
    argv = ["node", "-e", _LOADER, path] + list(args)
    assert all(len(a) < ARG_MAX_SAFE for a in argv if isinstance(a, str)), "node argv element over %d bytes" % ARG_MAX_SAFE
    return argv
