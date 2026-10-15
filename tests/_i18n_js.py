"""Real UI dictionaries for node-run JS tests: i18n_prelude() defines T/TV/U/... from web/js/05-i18n*.js + 06-i18n-*.js.

English is the source text, so a test that asserts Korean output has to run T() against the real I18N.ko.
The dictionaries run inside a closure (their globals do not clash with a test's own stubs); only the names asked for leak out.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = None


def _src():
    global _SRC
    if _SRC is None:
        d = os.path.join(ROOT, "web", "js")
        fs = sorted(f for f in os.listdir(d) if f.endswith(".js") and (f.startswith("05-i18n") or f.startswith("05a-i18n") or f.startswith("06-i18n")))
        parts = []
        for f in fs:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                parts.append(fh.read())
        _SRC = "\n".join(parts)
    return _SRC


def i18n_prelude(lang="LANG", names=("T", "TV", "U")):
    """JS that declares `const {T, TV, U} = ...` with the UI language taken from the JS expression `lang`."""
    return ("const {%s} = (function(__lang){ const UIS = {}, navigator = {language: 'ko'}, document = {getElementById: () => null},"
            " tabOwn = () => null, tabGet = (k, d) => d, SHOW_STEP = 50, softErr = () => {};\n%s\nLANG = __lang;\nreturn {%s}; })(%s);\n"
            % (", ".join(names), _src(), ", ".join(names), lang))


def i18n_switch(names=("T", "KE", "U", "TV")):
    """JS declaring `names` that follow the test's own `LANG` at call time (Korean and English dictionaries both loaded)."""
    body = i18n_prelude("__l", names).replace("const {%s} = (function(__lang)" % ", ".join(names), "return (function(__lang)", 1)
    return ("const __I18N = __l => { %s };\nconst __IK = __I18N('ko'), __IE = __I18N('en');\n%s\n"
            % (body, "\n".join("const %s = (...a) => (LANG === 'en' ? __IE : __IK).%s(...a);" % (n, n) for n in names)))
