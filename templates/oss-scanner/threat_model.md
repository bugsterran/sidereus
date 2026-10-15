<!-- Template: copy to your repo as .oss-scanner/threat_model.md (the path project.yaml names). Free text; the scanner reads it before it starts. Same headings as upstream templates/threat_model.md plus one optional section at the end. Replace every "e.g." line; delete guidance you do not need. -->
# Threat model

## What this project does and where untrusted input enters
- One or two sentences on what the project is and who runs it (library, CLI, local server, hosted service).
- List each entry point and who controls it: network requests, files it parses, environment, other processes, data fetched from elsewhere.
- e.g. "a compression library; we assume all input is untrusted"
- e.g. "a local web server bound to 127.0.0.1; any web page the user visits can send it requests"

## Components that matter most / least
- In scope: the code paths where a bug crosses a trust boundary.
- Out of scope: vendored or third-party code, examples, test fixtures, behaviour you document as intended.
- e.g. "the decoder matters; the compressor is less important but still in scope; the contrib/ directory is third-party and out of scope"

## How to exercise it
- Commands that run inside the image from the Dockerfile, offline: tests, drivers, a demo mode.
- e.g. "examples/ contains small drivers; test/ has the regression corpus"

## How you rate severity
- One line per level (critical / high / medium / low) with a concrete example from this project.
- Answer the borderline questions up front, e.g. "is post-auth SQLi high or critical?", "does local-only access lower the rating?"
- e.g. "any buffer overflow, use-after-free, or double free is high+ at a minimum. If the overflow is controlled and may lead to RCE then it should be critical. All DoS is medium."

## Anything to leave alone
- Known, documented behaviour and accepted risks, so they are not reported again.
- e.g. "do not report unaligned access in the SIMD code paths on x86"

## Report and patch preferences
- Optional. What a useful report contains (reproducer, affected commit), whether a patch is welcome, and where it goes (private advisory, email).
- e.g. "include a curl reproducer and the commit tested; a minimal patch is welcome in the private advisory"
