"""ast.parse of user code stays silent on invalid escapes; _atomic_write leaves no tmp on interrupt."""
import os
import shutil
import tempfile
import unittest
import warnings
from unittest import mock

from tests._load import sidereus

L = sidereus("structure_lang")
V = sidereus("arch_verify")
B = sidereus("bus")

# Invalid escapes: SyntaxWarning on 3.12+ (printed to viewer.err as `<unknown>:N:`).
SRC = 'def f():\n    return "\\{x\\}" + "\\9"\n'


class UserSrcSyntaxWarning(unittest.TestCase):
    def _strict(self, fn):
        with warnings.catch_warnings(record=True) as got:
            # ⚠the unittest runner prepends a "default" filter that would shadow the import-time one; keep only ours.
            ours = [f for f in warnings.filters if f[0] == "ignore" and f[2] is SyntaxWarning
                    and f[3] is not None and f[3].match(L._USER_SRC)]
            self.assertTrue(ours)
            warnings.filters[:] = ours
            warnings.filterwarnings("error", category=SyntaxWarning, append=True)   # any other SyntaxWarning fails
            warnings.filterwarnings("ignore", category=DeprecationWarning, append=True)   # 3.9 reports these escapes as DeprecationWarning
            out = fn()
        self.assertEqual([w for w in got if issubclass(w.category, SyntaxWarning)], [])
        return out

    def test_structure_lang_parses_silently(self):
        fns = self._strict(lambda: L._struct_py_fns(SRC))
        self.assertEqual([f["name"] for f in fns], ["f"])

    def test_arch_verify_parses_silently(self):
        V._py_ast.cache_clear()
        self.assertIsNotNone(self._strict(lambda: V._py_ast(SRC + "# av\n")))

    def test_own_compile_still_strict(self):
        # The filter is keyed on the pseudo-filename only: our own code paths still warn.
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            warnings.simplefilter("error", DeprecationWarning)
            with self.assertRaises(SyntaxError):
                compile(SRC, "own.py", "exec")


class AtomicWriteInterrupt(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_keyboard_interrupt_removes_tmp(self):
        with mock.patch.object(B.os, "replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                B._atomic_write(os.path.join(self.d, "x.json"), b"{}", prefix=".tmp-")
        self.assertEqual(os.listdir(self.d), [])


if __name__ == "__main__":
    unittest.main()
