"""scripts/room_log.py: one room's messages from a temp bus (R1), decision tags and slugs (R2), doc markers (R3, R4)."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tests._load import ROOT

_spec = importlib.util.spec_from_file_location("room_log_cli", os.path.join(ROOT, "scripts", "room_log.py"))
RL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RL)

S = 10**9
KO_TAG = "결정:"   # the Korean decision tag


def rec(i, t, room="room-a", frm="ann", subject="", body="hi", to=None):
    return {"id": i, "t": t, "from": frm, "to": to, "room": room, "subject": subject, "body": body,
            "thread": None, "kind": "msg", "replyTo": None}


class RoomLogTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="room-log-")
        self.bus = os.path.join(self.d, "bus.jsonl")
        rooms = os.path.join(self.d, "rooms.json")
        with open(rooms, "w", encoding="utf-8") as f:
            json.dump({"room a": {"members": []}, "a/b": {"members": []}, "a_b": {"members": []}, "room-a": {"members": []}, "room-b": {"members": []}, "room-empty": {"members": []}}, f)
        p = mock.patch.object(RL.mailbox_core, "ROOMS", rooms)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.d, True)

    def write(self, rs):
        with open(self.bus, "w", encoding="utf-8") as f:
            for r in rs:
                f.write(json.dumps(r) + "\n")

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = RL.main(list(args) + ["--bus", self.bus])
        return rc, out.getvalue().splitlines(), err.getvalue()

    def test_r1_only_room_in_order(self):
        """R1: only room-a, sorted by (t, id); DMs and room-b excluded; fields in order."""
        self.write([rec("00000003", 300 * S, body="third"), rec("00000002", 200 * S, room="room-b"),
                    rec("00000001", 100 * S, subject="Plan", body="line1\nline2"),
                    rec("00000004", 150 * S, room=None, to="bob"), rec("00000000", 300 * S, frm="bob", body="tie")])
        rc, lines, _ = self.run_cli("room-a")
        self.assertEqual(rc, 0)
        self.assertEqual(lines[0], f"# room=room-a slug=room-a after=- n=3 from={RL.fmt_t(100 * S)} to={RL.fmt_t(300 * S)}"
                                   f" until={300 * S} last=00000003 doc=-")
        self.assertEqual(lines[1].split("\t"), [RL.fmt_t(100 * S), "ann", "00000001", "", "Plan — line1\\nline2"])
        self.assertEqual([ln.split("\t")[2] for ln in lines[1:]], ["00000001", "00000000", "00000003"])

    def test_r1_since_cut(self):
        """R1: --since (ns or ISO) keeps only later messages."""
        self.write([rec("00000001", 100 * S), rec("00000002", 200 * S)])
        for since in (str(100 * S), RL.fmt_t(100 * S)):
            rc, lines, _ = self.run_cli("room-a", "--since", since)
            self.assertEqual(rc, 0)
            self.assertEqual([ln.split("\t")[2] for ln in lines[1:]], ["00000002"])
            self.assertIn(f"after={RL.fmt_t(100 * S)} n=1", lines[0])

    def test_r2_decision_tags(self):
        """R2: [D] for the Korean tag and `Decision:`, nothing for plain text."""
        self.write([rec("00000001", 1 * S, body=KO_TAG + " ship it"), rec("00000002", 2 * S, body="ok then. Decision: keep"),
                    rec("00000003", 3 * S, body="just talk")])
        _, lines, _ = self.run_cli("room-a")
        self.assertEqual([ln.split("\t")[3] for ln in lines[1:]], ["[D]", "[D]", ""])

    def test_r2_slug(self):
        """R2: unsafe characters become `_`; `..` / empty and unknown rooms exit 2."""
        self.assertEqual(RL.slug("a/b c"), "a_b_c")
        self.assertIsNone(RL.slug(".."))
        self.assertIsNone(RL.slug(""))
        self.write([])
        self.assertEqual(self.run_cli("..")[0], 2)
        rc, lines, err = self.run_cli("room-nope")
        self.assertEqual((rc, lines), (2, []))
        self.assertEqual(len(err.splitlines()), 1)

    def test_r3_from_doc_last_marker(self):
        """R3: only messages after the LAST marker, including an equal t with a different id."""
        self.write([rec("00000001", 100 * S), rec("00000002", 200 * S), rec("00000003", 200 * S), rec("00000004", 300 * S)])
        doc = os.path.join(self.d, "room-a.md")
        with open(doc, "w", encoding="utf-8") as f:
            f.write("## one\n<!-- room-minutes: room=room-a until=%d last=00000001 -->\n"
                    "## two\n<!-- room-minutes: room=room-a until=%d last=00000002 -->\n" % (100 * S, 200 * S))
        rc, lines, _ = self.run_cli("room-a", "--from-doc", doc)
        self.assertEqual(rc, 0)
        self.assertEqual([ln.split("\t")[2] for ln in lines[1:]], ["00000003", "00000004"])
        self.assertTrue(lines[0].endswith(f"n=2 from={RL.fmt_t(200 * S)} to={RL.fmt_t(300 * S)}"
                                          f" until={300 * S} last=00000004 doc={doc}"))

    def marker_from_header(self, header):
        """The marker the skill writes, built from the header fields as SKILL.md says."""
        f = dict(kv.split("=", 1) for kv in header[2:].split(" ")[:8])
        return "<!-- room-minutes: room=%s until=%s last=%s -->\n" % (f["room"], f["until"], f["last"])

    def test_r3_room_with_space_round_trips(self):
        """R3: a room name with a space writes a marker the next run parses (no duplicate section)."""
        self.write([rec("00000001", 100 * S, room="room a")])
        rc, lines, _ = self.run_cli("room a", "--doc-dir", self.d)
        self.assertEqual((rc, lines[0].split(" ")[1]), (0, "room=room%20a"))
        doc = os.path.join(self.d, "room_a.md")
        self.assertTrue(lines[0].endswith(" doc=" + doc))
        with open(doc, "w", encoding="utf-8") as f:
            f.write(self.marker_from_header(lines[0]))
        rc, lines, err = self.run_cli("room a", "--doc-dir", self.d)
        self.assertEqual((rc, len(lines), err), (0, 1, ""))
        self.assertIn(" n=0 ", lines[0])

    def test_r3_shared_slug_rooms_do_not_cut_each_other(self):
        """R3: `a/b` and `a_b` share a doc; each run uses only its own room's marker."""
        self.write([rec("00000001", 100 * S, room="a/b"), rec("00000002", 200 * S, room="a_b"),
                    rec("00000003", 300 * S, room="a/b")])
        doc = os.path.join(self.d, "a_b.md")
        with open(doc, "w", encoding="utf-8") as f:
            f.write("<!-- room-minutes: room=a%%2Fb until=%d last=00000001 -->\n"
                    "<!-- room-minutes: room=a_b until=%d last=00000002 -->\n" % (100 * S, 200 * S))
        _, lines, _ = self.run_cli("a/b", "--doc-dir", self.d)
        self.assertEqual([ln.split("\t")[2] for ln in lines[1:]], ["00000003"])
        _, lines, _ = self.run_cli("a_b", "--from-doc", doc)
        self.assertEqual(lines[1:], [])

    def test_r3_unparseable_marker_warns(self):
        """R3: a room-minutes comment that does not parse -> one stderr line, not a silent fallback."""
        self.write([rec("00000001", 100 * S)])
        doc = os.path.join(self.d, "room-a.md")
        with open(doc, "w", encoding="utf-8") as f:
            f.write("<!-- room-minutes: room=room-a until=soon -->\n")
        rc, lines, err = self.run_cli("room-a", "--from-doc", doc)
        self.assertEqual((rc, len(lines)), (0, 2))
        self.assertEqual(len(err.splitlines()), 1)
        self.assertIn("unparseable", err)

    def test_r4_nothing_new(self):
        """R4: nothing after the marker -> n=0 and no message lines; a known empty room is not an error."""
        self.write([rec("00000001", 100 * S)])
        doc = os.path.join(self.d, "room-a.md")
        with open(doc, "w", encoding="utf-8") as f:
            f.write("<!-- room-minutes: room=room-a until=%d last=00000001 -->\n" % (100 * S))
        rc, lines, _ = self.run_cli("room-a", "--from-doc", doc)
        self.assertEqual((rc, len(lines)), (0, 1))
        self.assertIn(" n=0 from=- to=- ", lines[0])
        rc, lines, _ = self.run_cli("room-empty")
        self.assertEqual((rc, len(lines)), (0, 1))
        self.assertIn(" n=0 ", lines[0])


if __name__ == "__main__":
    unittest.main()
