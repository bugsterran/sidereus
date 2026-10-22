# OSS Scanner template

Starter files for [Anthropic OSS Scanner](https://github.com/anthropics/oss-scanner), in the same format as its
`templates/` folder.

| File | Goes to | Notes |
|---|---|---|
| `threat_model.md` | `<your repo>/.oss-scanner/threat_model.md` | Free text the scanner reads first. Upstream headings plus an optional «Report and patch preferences». |
| `Dockerfile` | `<your repo>/.oss-scanner/Dockerfile` | Built with the repo as context. Network is on during the build only; the scan runs offline. |
| `project.yaml` | `<your repo>/.oss-scanner/project.yaml`, and `projects/<name>/project.yaml` in the oss-scanner repo | The enrolment file; its `dockerfile` and `threat_model` keys point at the two files above. |

## Use

1. `mkdir .oss-scanner && cp templates/oss-scanner/{threat_model.md,Dockerfile,project.yaml} .oss-scanner/`
2. Fill in every section of `threat_model.md`; keep the headings.
3. Adapt the `Dockerfile` so `docker build -f .oss-scanner/Dockerfile .` builds and runs the tests with no network after the build.
4. Enrol: follow the upstream [README](https://github.com/anthropics/oss-scanner#readme) and open a PR adding
   `projects/<name>/project.yaml` (filled from `project.yaml` here).

Sidereus's own filled copy is in [`.oss-scanner/`](../../.oss-scanner/).

## Inside Sidereus

The `security-checks` pipeline stage «threat-model review» reads `.oss-scanner/threat_model.md` from the project it
runs on, so the same file guides both the upstream scanner and the local review. Without that file the review still runs with a default
lens (authz bypass, injection, secrets, SSRF, unsafe file handling, state skips), and a project's own security
agent is used when the session has one.
