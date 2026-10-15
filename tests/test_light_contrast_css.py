"""Light-theme contrast fixes (WCAG AA) stay in the CSS."""
import pathlib
import unittest

CSS = pathlib.Path(__file__).resolve().parent.parent / "web" / "css"


class LightContrast(unittest.TestCase):
    def test_values(self):
        s = (CSS / "91-light.css").read_text(encoding="utf-8")
        for v in (".acc0{--acc:#0a666c}", ".acc5{--acc:#5b7414}", ".acc2{--acc:#8a5600}", ".acc3{--acc:#1b7a43}", "#b45309 60%,var(--nx-t1))}"):
            self.assertIn(v, s)
        b = (CSS / "96b-automation-banner.css").read_text(encoding="utf-8")
        self.assertIn("[data-theme=light] #autobar{opacity:1}", b)


if __name__ == "__main__":
    unittest.main()
