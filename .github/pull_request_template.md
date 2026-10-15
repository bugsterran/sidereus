**What and why**

**Gates** (CI runs the same)
- [ ] `for f in chat_server.py sidereus/*.py; do /usr/bin/python3 -m py_compile "$f"; done`
- [ ] `for f in web/*.js web/js/*.js; do node --check "$f"; done`
- [ ] `bash tests/run.sh`

**Checklist**
- [ ] Written with AI help (say so either way; see CONTRIBUTING.md)
- [ ] Includes a failing test or reproduction that this PR fixes
- [ ] One change only
- [ ] Adapter PR: `bash tests/run.sh -p test_adapter_contract.py` passes
- [ ] Checked on the rendered page, not only `/api/...`
- [ ] Metadata only: no conversation text on the page or in MCP answers
- [ ] No new dependencies
- [ ] New UI strings have an English entry in `I18N.en`
- [ ] Screenshots (if any) taken with `--demo`
