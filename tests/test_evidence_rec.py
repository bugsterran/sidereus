"""scripts/evidence_rec.py: one v1 record per gate run, robust to bad input, rotated at the cap.

Temp paths only; ts is passed in.
"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts', 'evidence_rec.py')
_spec = importlib.util.spec_from_file_location('evidence_rec', _P)
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


class EvidenceRec(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.out = os.path.join(self.d, 'evidence.jsonl')
        self.tsv = os.path.join(self.d, 'steps.tsv')

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _w(self, path, text):
        with open(path, 'w') as f:
            f.write(text)

    def _lines(self):
        with open(self.out) as f:
            return [json.loads(x) for x in f.read().splitlines()]

    def _run(self, *extra, rc='0', mode='fast', ts=1000):
        return ev.main([self.out, mode, rc, self.d, 'abc1234', '1', self.tsv] + list(extra), ts=ts)

    def test_valid_tsv_one_record(self):
        self._w(self.tsv, 'py_compile\t0\t140\t0\t2\ntests\t1\t900\t3\t40\n')
        self.assertEqual(self._run(rc='1'), 0)
        recs = self._lines()
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual((r['v'], r['kind'], r['ts'], r['mode'], r['rc'], r['head'], r['dirty']),
                         (1, 'check', 1000, 'fast', 1, 'abc1234', True))
        self.assertEqual(r['repo'], os.path.realpath(self.d))
        self.assertEqual(r['steps'][1], {'name': 'tests', 'rc': 1, 'n': 900, 'failed': 3, 'secs': 40})
        self.assertNotIn('screen', r)

    def test_malformed_and_missing_tsv(self):
        self._w(self.tsv, 'garbage line\nbad name!\t0\t1\t0\t1\nok\tx\t1\t0\t1\nnode\t0\t50\t0\t1\n')
        self.assertEqual(self._run(), 0)
        os.remove(self.tsv)
        self.assertEqual(self._run(), 0)
        recs = self._lines()
        self.assertEqual([s['name'] for s in recs[0]['steps']], ['node'])
        self.assertEqual(recs[1]['steps'], [])

    def test_checks_modes_recorded(self):
        self._w(self.tsv, 'ruff\t0\t12\t0\t1\n')
        self._run(mode='checks-quality')
        self._run(mode='checks-security', rc='1')
        self._run(mode='checks-other')
        recs = self._lines()
        self.assertEqual([(r['mode'], r['rc']) for r in recs], [('checks-quality', 0), ('checks-security', 1)])
        self.assertEqual(set(recs[0]), {'v', 'kind', 'ts', 'mode', 'repo', 'head', 'dirty', 'rc', 'steps'})

    def test_bad_args_write_nothing(self):
        self.assertEqual(ev.main([self.out, 'weird', '0', self.d, '', '0', self.tsv], ts=1), 0)
        self.assertEqual(ev.main([self.out], ts=1), 0)
        self.assertEqual(self._run(rc='nope'), 0)
        self.assertFalse(os.path.exists(self.out))

    def test_rotation_keeps_last(self):
        self._w(self.tsv, '')
        for i in range(ev.EV_CAP + 1):
            self._run(ts=i)
        recs = self._lines()
        self.assertEqual(len(recs), ev.EV_KEEP)
        self.assertEqual(recs[-1]['ts'], ev.EV_CAP)
        self.assertFalse(os.path.exists(self.out + '.tmp'))

    def test_screen_attached_and_sanitised(self):
        self._w(self.tsv, 'screen\t0\t6\t0\t30\n')
        sc = os.path.join(self.d, 'screen.json')
        self._w(sc, json.dumps([{'w': 900, 'lang': 'ko', 'ok': True, 'diff': 0, 'text': 'x'},
                                {'w': 1100, 'lang': 'en', 'ok': False, 'diff': 2}, {'w': 'bad'}]))
        self._run(sc, mode='full')
        r = self._lines()[0]
        self.assertEqual(r['screen'], [{'w': 900, 'lang': 'ko', 'ok': True, 'diff': 0},
                                       {'w': 1100, 'lang': 'en', 'ok': False, 'diff': 2}])
        self._w(sc, '{not json')
        self._run(sc, mode='full')
        self.assertNotIn('screen', self._lines()[1])


if __name__ == '__main__':
    unittest.main()
