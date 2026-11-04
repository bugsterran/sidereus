"""Every «Confirm — send» button carries .archok, the class 05-controls.css paints as the primary action.

Without it the button keeps the neutral segment look and reads as disabled next to «Cancel».
"""
import pathlib
import re
import unittest

WEB = pathlib.Path(__file__).resolve().parent.parent / 'web' / 'js'


class ConfirmSendPrimary(unittest.TestCase):
    def test_confirm_send_buttons_are_primary(self):
        seen = 0
        for f in sorted(WEB.glob('*.js')):
            if f.name.startswith('06-i18n'):
                continue
            src = f.read_text(encoding='utf-8')
            for m in re.finditer(r"T\(\s*[^)]*'Confirm — send'", src):
                start = src.rfind('<button', 0, m.start())
                if start < 0:
                    continue
                tag = src[start:src.find('>', start)]
                seen += 1
                self.assertIn('archok', tag, '%s: «Confirm — send» button without .archok' % f.name)
        self.assertGreaterEqual(seen, 6)

    def test_css_paints_archok(self):
        css = (WEB.parent / 'css' / '05-controls.css').read_text(encoding='utf-8')
        self.assertRegex(css, r'\.wkrgb\.archok:not\(\[disabled\]\)\{background:var\(--nx-info-bg')


if __name__ == '__main__':
    unittest.main()
