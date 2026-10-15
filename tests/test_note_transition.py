"""_note_transition: end commands raise no card; the task line is cleaned before it goes on a card."""
import unittest
from unittest import mock

from tests._load import sidereus

notes = sidereus("notes")

EXIT = "<command-name>/exit</command-name> <command-message>exit</command-message> <command-args></command-args>"


class NoteTransitionTest(unittest.TestCase):
    def setUp(self):
        self.added = []
        self.p = [mock.patch.object(notes, "_card_add", lambda *a, **k: self.added.append(a)),
                  mock.patch.dict(notes._prev_state, {}, clear=True)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def _go(self, end, task, reply=""):
        base = {"sid": "s1", "cwd": "/w", "project": "w", "task": task, "reply": reply}
        notes._note_transition(dict(base, state="tool"))
        notes._note_transition(dict(base, state=end))

    def test_end_commands_raise_no_card(self):
        for cmd in ("exit", "clear", "quit"):
            for end in ("abort", "ask"):
                self.added.clear(); notes._prev_state.clear()
                self._go(end, EXIT.replace("exit", cmd))
                self.assertEqual(self.added, [], (cmd, end))

    def test_other_command_card_has_no_text(self):
        # rule 1 (2026-09-25): neither the instruction nor the reply goes on the card body
        self._go("abort", "<command-name>/review</command-name> <command-message>review</command-message>",
                 reply="SECRET reply")
        self.assertEqual(self.added[0][3], "")
        self.assertEqual(notes._task_line("<command-name>/review</command-name>"), "/review")

    def test_empty_task_writes_no_prefix(self):
        self._go("ask", "")
        self.assertEqual(self.added[0][3], "")

    def test_long_task_cut_at_word(self):
        body = notes._task_line("fix the " + "notification popover clipping " * 4)
        self.assertTrue(body.endswith("…"))
        self.assertTrue(body[:-1].endswith(("clipping", "popover", "notification")), body)
        self.assertLessEqual(len(body), notes.TASK_MAX + 1)


if __name__ == "__main__":
    unittest.main()
