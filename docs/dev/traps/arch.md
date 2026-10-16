# Traps — Structure tab (Architecture · Size)

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Structure tab (Architecture · Size)

- ⚠**An unquoted SVG attribute right before `/>` swallows the slash** (2026-10-09). `ry=5/>` parses as `ry="5/"` and logs «Expected length» on every paint (arch legend swatches). ⇒ Put a space before `/>` or quote the value. The demo had no arch map, so only the live console showed it.
- ⚠**`ast.parse` on a user's repo prints SyntaxWarning to viewer.err on Python 3.12+** (2026-10-13). Invalid escapes like `"\{"` in the analysed project's own files surfaced as `<unknown>:26: SyntaxWarning`. ⇒ structure_lang and arch_verify parse with the pseudo-filename `<user-src>`, and a module-level `filterwarnings("ignore", SyntaxWarning, module="<user-src>$")` silences only those. ⚠Not `catch_warnings` — it is not thread-safe. Test: `test_user_src_warnings.py`.
- **Anything new drawn by `archPaint` must join its paint signature** (`84j` `archPaint` `sig`, `84l2` `archReqSig`).
  - Cause: the poll repaints every state; an unchanged `sig` keeps the cached DOM, so a field not in it (request record state/stage, stop preview) never repaints.
  - ⇒ Add the rendered value to `sig` (84l2 rows go through `archReqSig`).
  - ⚠Guard calls into 84l/84l2 with `typeof`: `tests/test_struct_arch_js.py` loads 84j without them.
- **A Sidereus stop also blocks a hand-started run of that pipeline for 30 min** (`hooks/pl_guard.py` `STOP_PENDING_S`).
  - Cause: with no open run, the marker `DATA_DIR/plstop/<sid>.json` denies any tagged dispatch of that pipeline until it expires — the stop may arrive before the run opens.
  - ⇒ A new Sidereus request for that pipeline lifts it (`pl_reqs.record`); the deny text names the request id.
- **Band index comes from `archBandPlan`, never `ARCH_LAYERS.indexOf(m.layer)`** (`84j2` `archBandPlan`/`archBandSrc`/`archBandFix`, `84j4` `archFocusPlan`/`archFocusBuild`).
  - Cause: feature-package maps spread one feature over five layer bands; loc styles (`feature-pkgs` · `apps` · ...) draw 4 bands L0 Entry · L1 Client · L2 Server (Code with no client) · L3 Stores, then Lx.
  - ⇒ Every band index, title and hover tip goes through the plan (`of` · `lbl` · `tip`); `bp.n` is the external band. `archKey` adds `\tloc` so cached layer-mode drawings are not reused.
  - ⚠Layer styles and a missing style must emit byte-identical source (stored screens); no plan passed = old layer path, no band tips. Band titles ≤ 28 chars.
- **Layered view: cross-band lines must enter the target top, not its sides** (`81g` `mmdRouteAll` `bandPens`, `81g0` `G.spen`/`G.tpen`).
  - Cause: with free node ports a side entry (`RR_SIDEIN` 2) was cheaper than the turn into a top port (`RR_TURN` 3), so a hub's callers bussed into its left/right sides.
  - ⇒ Both ends in `pass` bands: other band below → source bottom only, target top only (reverse for above); same band → sides when rows overlap, else by relative y. No route with strict ports → target ports relaxed, then both, before the elbow fallback.
  - ⚠A group inside a pass band needs `PORTGAP` (16px, `81e` `mmdLayout`) more under its title: with 8px a first-row box under a wider title had no top port (★real focus Security/auth → Main RDB entered the left side); 8 extra still failed, 24 pushed the 1100 focus hub past the first screen (406 > 400).
  - ⚠Graphs without `pass` must route byte-for-byte as before (`tests/test_mermaid_band_ports_js.py`); reset `G.spen` per edge and after the loop.
- **«Not on a traced flow» sub-fold keys must be in both Expand all and the unpin check** (`84j6` `archEdTreeClick`).
  - Cause: Other rows sit under two folds (`p\tother` and `p\tother.w` / `p\tother.c`); a key missing from Expand all leaves rows hidden, missing from the unpin check leaves the map lit with no visible row.
  - ⇒ Expand all sets `other`, `other.w`, `other.c`; a pinned Other row unpins when `other` or its own sub-fold goes open → closed.
  - ⚠`data-aet` values `other.w`/`other.c` must not reach the numeric flow-pin branch (`/^\d+$/`).
- **Fix-request recipient: `repos` sessions are tier 1 «Uses this repo», never tier 0** (`84l` `archChkFixCands`).
  - Cause: `repos` lists every repo a session touched, so treating it as «This project» put unrelated sessions on top; excluding it left the button dead when no session ran in the repo.
  - ⇒ Tiers 0 cwd/under/worktree · 1 `repos` · 2 other live cc sessions; the DM body names the target repo (`Target repository: <p>`); last pick per repo in `sidereus.ckfix`.
  - ⚠Never move `repos` into tier 0, and never start a session — live sessions only.
- **Module «Files» list takes the path from the map, not the request** (`sidereus/arch_map.py` `files`).
  - Cause: a client-sent path or commit would let any request list any tree of an allowed repo, and a git pathspec turns `:`/`-`/glob text into magic.
  - ⇒ Only `path` + module `id` come in; the path is read from the newest re-validated map, checked by `_mod_prefix`, and matched in Python (`rel == p or rel.startswith(p + "/")`) against a cached `ls-tree`.
  - ⚠Never pass the module path to git (no pathspec) — `sidereus` would also match `sidereus2/` with a bare `startswith`.
- **map.json v2 rules switch on `v`** (`sidereus/arch_schema.py` `_groups_errors`/`_mod_v2_errors`).
  - Cause: v1 maps must stay valid byte-for-byte, so v2 keys (groups, layer, group, summary, owns) and kinds (entry/store, read/write/serve/event) count as unknown when `v` is 1.
  - ⇒ v2 checks live only in the v2 branch; `owner_of` takes read/write evidence from `from` and serve evidence from `to`.
  - ⚠entry/store modules own no repo files, so read/write starting at an entry, or serve ending at a store, can never pass the owner check — the schema now refuses them with a reason (read/write must start, serve must end, at a kind:module).
  - ⚠A list-valued `id`/`kind`/`from`/`to` raised TypeError (set/dict lookup) out of `schema_errors`; it is now refused as «must be a string» first.
  - ⚠Schema checks live in `arch_schema.py` (split off `arch_verify.py` at the 620-line cap, `tests/test_arch.py` PY_FILE_CAP); `arch_verify` re-exports its names — add schema rules there, not in `arch_verify`.
- **Grid router lives in 81g0, not 84b** (`web/js/81g0-structure-grid-router.js`, used by 81g mermaid edges).
  - Cause: 81g routes with `relGridOf`/`relRoute`/`relLanes`/`relOccMark`/`relOrthoD`/`relSimp`/`RR_C`, which lived in the removed relations file 84b.
  - ⇒ The router closure moved unchanged to 81g0. `81g-` sorts before `81g0`, so 81g runs first and reads `RR_C` and the router only inside functions.
  - ⚠Never read `RR_C` or call a router function at 81g's top level — it is undefined there.
  - ⚠A* costs are Float32 (`B.g`): compare fractional costs through `Math.fround`, or states are discarded and the route falls back to a curve (★2026-09-27).
  - ⚠`relOrthoD(p, hit)`: the S-curve over a short jog cuts corners the orthogonal route went around (★2026-10-05: 66 lines through other cards) — pass `hit` when boxes can sit beside the jog.
- **Architecture overview: entries on top — v1 maps only** (`84j` `archRanks` → `g.rankFix`, 81f `mmdFixed`). Layered v2 maps rank by band (`84j2` `archBandFix`).
  - Cause: `mmdRank` slid sources and sinks to whatever layer packed best, so entry modules were not on the top row.
  - ⇒ The overview passes fixed ranks: DFS back edges ignored, longest path from entries, External box one below; sinks are not pinned.
  - ⚠Every root item (nodes and the `xg` box) needs a finite rank, or 81f silently drops `rankFix` and the old layout returns.
  - ★2026-10-12 `mmdQuality` self-map with fixed ranks: 2 crossings, 912×874 (was 2, 1160×700); pinning sinks to the bottom measured 2 → 6, so it was not adopted. Demo shop map 0 → 0.
- **Layer bands are pass-through walls** (`84j2` `archBandFix` sets `g.sgs[L*].pass`; 81g router + `mmdQuality`).
  - Cause: a band is a subgraph, so every line between two non-adjacent layers counted as crossing a box and the router walled it off.
  - ⇒ `pass` bands are skipped as walls and as box hits; band titles, group boxes and nodes stay walls.
  - ⚠Bands stay `direction TB`: in an LR block 81f ranks along x, so unlinked groups stacked in one column (★2026-10-14 self-map 1795×6581 vs 5012×2204).
  - ⚠Every root item needs a rank (bands only) or 81f drops `rankFix`.
  - ★2026-10-14 self-map (95 modules, 110 drawn pairs), after the tag-mode `mmdLabels` skip: banded 232ms layout (was 2084ms), 0 box hits, ~859-874 crossings (uncross is time-limited) vs v1 path 155 crossings, 97ms (was 225ms) — long read/write lines down to the data band dominate.
- **Flow entry nodes use `en<n>` keys, never `m<i>`** (84k `archFlowEntries`, 84j2 `archBandSrc`).
  - Cause: `archDgClick`, `archChkPaint` and `archMmd` tips index `mods` by `+key.slice(1)`; an `m`-style key would hit a real module.
  - ⇒ Entry nodes are `en<n>`; `archDgClick` acts only on `/^m\d+$/`; `archLitSet` rebuilds the same keys with `ARCH.tests`.
  - ★2026-10-14 self-map (95 modules, 8 flows → 8 entries): crossings 822 → 814, box hits 0 → 0, width 4969 → 7029px (one L0 row; full labels were 7596px, so node labels are cut at 24 chars).
  - ⇒ With entries, L0 turns `direction LR` and holds one pass-through row `Ek<k>r<r>` (≤ 8, `.archerow`) per kind (http · hook · event · job · cli · mcp · file · other); entry modules join their `ext` row, groups set `TB` back — ~257px per entry made 40 entries ~15k px wide. ⚠No entries: old bytes.
  - ⚠Rows stack in kind order only through the opt-in 81f `mmdPlace` `one` (sg flag `oneLayer`): one layer, source order, each row centred in the entry band, title centred. 81f is the shared placer, so never make it the default — without it an edge between two rows ranks them side by side and kinds interleave by neighbour position.
  - ★2026-10-15 real store (64 modules, 22 flows, style feature-pkgs = location bands as the viewer draws it), left edge → centred: overview crossings 248 → 241, box hits 0 → 0; focus on its security filter module 6 / 0 unchanged. (Layer bands, style dropped: 256 → 254, box hits 19 → 25.)
- **Dependency direction ≠ request order** (84j2 `archFront`, 81f `mmdPlace` `front`, 79 `data-k=uses`).
  - Cause: every controller calls the request filter (`f1 → security`), so ranking by call direction drew the filter under the controllers it runs before.
  - ⇒ Front modules = not entry/external, with a passed `serve` edge from a kind-entry module or a flow's first step on them. 81f puts every front module of a block on rank 0 — one shared row even when one calls another (★real store: two rows, y 928 / 1006, before) — and ranks the rest with edges into front modules reversed (ranking only, arrows unchanged); module → front call pairs draw as thin dashed `uses`. Layer mode lifts a front module below the api band into it; location mode keeps its band.
  - ⚠Opt-in through `g.front` (set by `archBandFix` only when a front module is drawn): a map with no such `serve` keeps its bytes.
  - ⇒ Bands share one vertical centre axis (81e `g.axis`, root block only, set by `archBandFix`); focus passes the hub (`g.axisHub`) so it sits on the axis instead of its band's centre. ★real store overview 278 → 217 crossings, box hits 0 → 0, width 2670 → 2626.
  - ★2026-10-15 same real store, location bands: overview crossings 241 → 278, box hits 0 → 0, width 2662 → 2670; focus on the security filter crossings 6 → 1, box hits 0 → 0, width 1713 → 1469.
- **Arch map edges need a hit path** (84j `archDgClick`, 81e `mmdSvg`, 79 `.mmdhit`).
  - Cause: a 1.1px edge stroke is nearly impossible to click.
  - ⇒ Tag mode puts a transparent 10px `.mmdhit` copy of each line (same `d`) first in its `.mmdfe` group; a click maps `data-f`/`data-t` to the first passed edge and toggles `ARCH.op`.
  - ⚠Tag mode only — untagged `mmdSvg` output is sha256-pinned (`test_svg_untagged_pinned`); do not add it to the shared path.
- **Picker popover vs. the morphed toolbar** (2026-10-08, 80 `paintStruct`, 08b).
  - Cause: `#tbstruct` is patched by index (`morphHtml`); a poll that changes the chip count would turn the «Projects ▾» node into a chip and drop its focus/`aria-expanded`.
  - ⇒ Chip markup is `<b>` · `<span class=ppcs>` · button (fixed index), and the patch is skipped while `#ppop` is open.
  - ⚠Do not put chips directly beside the button again or remove the open-popover skip.
- **Arch hover dims with opacity** (2026-10-07, 84j `archHovPaint`).
  - Cause: like `.reldim`, hover-only dimming needs the rest of the map pushed back.
  - ⇒ `svg.archdim` uses opacity only while the pointer is on the map; colours are class-only on the cached SVG.
  - ⚠Never copy it into an always-on state (contrast 4.5:1). ⚠Never rebuild innerHTML on hover — it resets `.archmap` scroll.
- **Arch path/flow highlight uses its own classes** (2026-10-14, 84j3 `archLitPaint`, 79 `svg.arlitdim`).
  - Cause: hover clears `.arn`/`.archdim` on pointer-out (`archHovPaint(svg, null)`), so a highlight sharing them vanished on the first mouse move.
  - ⇒ `.arlit` on nodes/edges + `svg.arlitdim`, re-applied after every paint and fill (`archLitNow`); hover rules win while the pointer is on the map.
  - ⚠Always-on state: colour only, no opacity (contrast 4.5:1). ⚠Do not reuse the hover classes.
- **Overview reduce may hide cross-layer pairs; the detail panel lists them** (84j `archReduce`, 84j3 `archNbrTree`). ★2026-10-14 self-map: keeping them = 3000 crossings / 133 box hits (was 726 / 0) — ⚠do not exempt them from the reduction.
- **Edge-row hover state is `var ARCH_EVL`, not `let`** (84j5; 84j3 `archLitQ` reads it).
  - Cause: all `web/js` files are one inline script; 84j3 runs before 84j5, and a `let` read in its TDZ throws.
  - ⇒ Keep `var`. 84j5 adds a second capture-phase `scroll` listener on `.archmap` (marker `.archoff`) next to 84k's count one; each throttles with its own rAF.
  - ⚠Neither may scroll; a stale `ARCH.op`/hover index after a refetch falls back to lit flow / scope in `archLitQ`.
- **Arch minimap: clone once per svg key, rAF on scroll, sit outside `.archmap`** (84j7, 79c `.archmm`). ⚠Re-cloning on scroll/hover stalls large maps; inside `.archmap` a press starts the drag-pan; `.archmap` is pinned to grid cell 1/1 or the overlay pushes it to the next cell.
- **Arch map scrolls once per map identity, never per svg key** (84j7 `archMmFirst`, `ARCH_MM.seen`). ⚠The svg key changes with selection / full / lit — keying the first scroll on it moves the view on clicks; only an overview at scroll 0,0 moves, and a hidden (zero-size) paint is not marked seen.
- **First sight anchors the map, it does not centre it** (84j7 `archMmAnchor`).
  - Cause: centring a map larger than the view put its middle on screen and clipped the Entry band (top-left) out of sight.
  - ⇒ top = map.y − sticky `.archtop` height; left = centred only when the map fits the width, else map.x.
  - ⚠Do not go back to the map centre for the first scroll; clicks, expands, lit flows and polls still never scroll.
- **Arch map scroll is kept per project; the toolbar is sticky** (2026-10-14, 84j `archPaint` `box._arp`, 79 `.archtop`).
  - Cause: the repaint copied `.archmap` scroll from whatever was on screen, so project B opened at A's scroll (★2424, 949); bar/legend scrolled away on a ★4865×2438 banded map.
  - ⇒ Scroll is copied only when `box._arp` is the same project; bar, «No layers» notice and legend sit in one sticky `.archtop` (top/left = minus the scroller padding).
  - ⚠Do not drop the same-project keep — poll repaints and clicks must not move the view.
- **Arch focus view fits a room measured from `.archmap`** (2026-10-14, 84j `archFitOf`, 81f `mmdPlace` room) — v1 maps only (v2 focus keeps the bands, 84j4).
  - Cause: the room is `.archmap` offsetWidth/Height. It is bounded only because `.archbody` is flex `1 1 auto` with `min-height:0`.
  - ⇒ Only spacing grows (row gap at most 120, layer gap at most 480). Room is in 20px buckets, so a refit happens only when the bucket changes; resize is debounced 160ms. ★demo 1440×900: 570×218 → 936×458, boxHits 0.
  - ⚠If that parent ever sizes to its content, a bigger drawing grows the room, which grows the drawing again: a loop. ⚠Do not use clientWidth/Height (a scrollbar would flip the bucket).
- **Arch focus out-edge labels piled up at the hub** (2026-10-14, 81e `mmdFlPlace`, 84j `g.flHead`) — v1 maps only (v2 focus hides labels until hover).
  - Cause: label anchor = 16px along the first run (the tail); every out-edge's tail is the hub, so all labels competed for the hub stub. Fallback badges also ignored placed labels.
  - ⇒ Focus sets `g.flHead = me`; its out-edges anchor 28px before the head. Badges take the nearest free candidate first. ★6-out test graph: overlaps 2 -> 0, label-on-other-line 7 -> 0, badges 1 -> 0.
  - ⚠Do not set `flHead` in the overview or anchor in-edges at the head — their tails differ, and the overview SVG must stay byte-equal.
  - Badge with no free candidate fell back to the anchor, ignoring nodes and labels (★m20: ① covered m19 by 7px) · ⇒ slide along the edge (4px steps) first, anchor last · ⚠never move the candidate-first order, or no-overlap badges shift.
  - ⚠With `flHead`, in-edge labels are placed before out-edge labels. In edge order, head-anchored out-labels took the in-labels' spots by each caller. ★self-map m0: 20/37 in-labels moved, 4 badges; with in-labels first, 6 moved, 0 badges.
- **Arch focus keeps the bands; labels hover-only** (2026-10-14, 84j4 `archFocusSrc`, 79 `.archdg[data-fv]`).
  - Cause: the LR star dropped the layer bands, so a focused module lost where it sits; every edge label drawn at once piled up at the hub.
  - ⇒ v2 focus redraws the clicked module + direct neighbours inside the top-level bands and group boxes; infra/shared neighbours fold into one `ifx` chip (n>=2). Labels show only as lit flow step numbers (`.arlit`) or on edge hover: box hover = no text (edges lit only), edge hover = that one pill (`.arhe`, solid).
  - ⚠Do not reduce focus pairs (`archReduce`) — the focus view is where every direct edge is shown.
  - ⚠Do not fold externals into the chip — they are the store end of flows, and a lit flow would end on a hidden node.
- **Focus width needs a layout-and-shrink loop — row packing alone overflows** (2026-10-14, 84j4 `archFocusSrc`).
  - Cause: long-edge dummies and barycentre offsets widen rows after packing. ★rows that fit drew 844px in a 680px room.
  - ⇒ `archFocusSrc` lays out, then shrinks the row budget and retries (max 4 tries, memoised).
  - ⚠Do not drop the loop for a pure row-packing estimate.
- **A wrapped caller rank pushes the hub off the first screen** (2026-10-14, 84j4 `archFocusBuild` `hubTop`).
  - Cause: the shrinking row budget also wrapped the rank above the hub inside its own band; a mutual neighbour (calls and is called) stayed in that rank. ★1100 pane: hub box 851-881, first screen ends at 860.
  - ⇒ Ranks above the hub keep the full room; if still too wide, mutual neighbours move below the hub (hub listed first so the renderer's DFS cycle break starts at it, plus `hub ~~~ m`). ★svg hub y 456 -> 382 (= 1440's).
  - ⚠The invisible edge alone does not move them — the renderer's cycle break keeps the mutual one above unless the hub comes first in the source.
  - ⚠The limit is the map pane bottom (~819 at 860 high), not 860, and the chrome above the svg counts as much as the layout: the svg scale is 1:1, so svg y + svg top = screen y. The path wrapping to 2 lines (+28px at 1100) and the «Source text» row (25px) kept the hub at 824-854. ⇒ 79 `.archpath` nowrap (only the group crumb shrinks to «…») and the focus `.mmdbar` floats (height 0, `align-items:flex-start` or the button stretches to 0). ★hub 792/824/748 -> 767/771/723 (900/1100/1440).
- **Arch overview hover ≠ all neighbours** (2026-10-07, 84j `archReduce`).
  - Cause: the overview drops implied pairs (★self-map crossings 109 -> 2), and hover reads edges from the drawn SVG.
  - ⇒ Bar hint counts the hidden pairs; «All edges» (`ARCH.full`) or a click (focus view) shows every direct edge.
  - ⚠Do not reduce the focus view or feed reduced pairs to the edge list / in-out counts.
- **pl_model `ag` chosen by index hid agents** (2026-10-07, `pl_runs.py`).
  - Cause: `i < 2` — two newer ended runs took both slots, so the open run behind them showed no agents.
  - ⇒ `ag` goes to the newest 3 open runs + the newest ended run (by status, not index).
- **Arch map: a missing file read as an empty file** (2026-10-07, `arch_verify`).
  - Cause: `_git_run_capped` hides the exit code, so `git show <commit>:<missing>` returns "" like an empty file.
  - ⇒ The commit's file set comes from one `ls-tree -r --name-only -z`; a path outside it is `nofile` before any `show`.
  - ⚠Mermaid node ids in map.md are `n0..nN`, never module ids — `.`/`-` in an id are read as edge syntax.
  - ⚠Evidence counts only inside the edge's owner module (`from`; `to` when `from` is external; plan.json globs, else `path`) — symbol-only matching passed 48/48 live.
  - ⚠Labels swap `" | < > # & \`` for look-alikes, never `#NN;` entities — the page's flowchart parser (81e) shows those raw.
  - ⚠`arch_map` copies `ARCH_DIR` by value: tests patch `arch_map.ARCH_DIR` and `arch_verify.ARCH_DIR` separately.
- **Check runner: spawning and stored fields** (`arch_checks`, `scripts/arch_checks.py`).
  - ⚠Sidereus never runs a tool (rule 7): `sidereus/arch_checks.py` has no subprocess; only the pipeline runner spawns, in its own process group (killed whole on timeout).
  - ⚠Only file / line / rule / severity (+ package) are stored — `checks_errors` refuses unknown keys and `load_checks` re-drops bad rules and `..` paths.
  - ⚠`--category security` is required: without it the runner and gate exit 1 (the lint category was removed; an old gate must not pass on nothing).
- **Security checks: secrets and network** (`sec_checks`, `scripts/arch_checks.py --category security`).
  - Cause: a gitleaks report carries `Secret` / `Match` / `Line` (redacted or not); npm audit and osv-scanner fail without network and would read as «0 advisories».
  - ⇒ `parse_gitleaks` reads `RuleID` / `File` / `StartLine` only; the report sits in the runner's temp dir and `take_report` deletes it in `finally`. Advisory tools run only with `--net`; a DNS/connect error is `skipped «needs network»`.
  - ⚠Never store, log or relay `Secret` / `Match` / `Line` / message (bandit: `code`, `issue_text`) — not even in `why`.
  - ⚠gitleaks writes `[]` even when it read nothing: «did work» needs its `scanned ~N bytes` with N > 0, else files 0 (gate EMPTY).
- **Arch flows must not move the gate** (`arch_flow`, `scripts/arch_verify.py`).
  - Cause: flows ride the same gate run as edges; a flow error or failing step could flip the pipeline's onFail loop.
  - ⇒ `AF.run` only returns a suffix ("" without flows.json or with an invalid map); the CLI wraps it so any exception only changes the suffix.
  - ⚠Never fold flow steps into `rate` or `rc`. ⚠In the page's sequence diagram, `data-i` = step index + 1 (item 0 is the entry arrow).
- **Arch map: broad globs and undefined symbols passed edges** (2026-10-07, `arch_verify`).
  - Cause: a file matched by two modules' globs (or `**`) backed edges of either; an X->Y import/call passed on any symbol present in X.
  - ⇒ Files owned by >= 2 modules are `contested` (why `overlap`, reported in verify.json); module->module import/call needs the symbol defined in `to` (path component, else `git grep` + definition-line regex; why `nodef`).
  - ⚠Config/DI and external ends are exempt — HTTP / cross-language wiring must be drawn as kind=config. ⚠A git grep error means not defined (fail-closed).
  - ★A URL symbol (`/codebook`, `://`) skips `nodef` and the edge is estimated (`is_route`, `est_of`): without it a real Spring + frontend project map went 73/73 → 59/73, all 14 drops being real FE→BE HTTP calls.
- **Arch flow HTTP hop proved nothing about the BE route** (`arch_flow.verify_flows`, why `noroute`).
  - Cause: a module->module step with a URL symbol skipped `nodef`, so any FE call passed to any BE module.
  - ⇒ Such a step needs `to_evidence` (the BE mapping line, a file owned by `to` only); `_be_routes` joins class/`prefix=` prefixes with method paths within ±ARCH_K and `route_match` compares from the end.
  - ⚠The suffix match is a heuristic (base paths, params, open `/x/` + id tails), not router resolution. ⚠Express mounts (`app.use('/api', router)`) in another file are not resolved.
  - Stores drawn before this check have no FE->BE steps, so nothing regresses; redraw the map to get them.
- **Arch `nodef` missed class attributes, import aliases and file names** (2026-10-12, `arch_verify.defined_in`).
  - ★9/87 flow steps of the Sidereus map were false `nodef`: `_GET_ROUTES` (class-body attr), `pipeline_save` (`save as pipeline_save`), `index.html` (cut to `html`).
  - ⇒ (`ast`, .py only, unparsable = no) class-body Assign/AnnAssign/def counts; an import `X as sym` in the evidence file checks `X` in `to` only when its module is a file of `to`; a symbol equal to an owned file's name/path is defined.
  - ⚠Shared by map edges and flow steps (`defined_or_alias`) — change it once. Negative tests: undefined attr, alias to a missing name, file not in `to`.
  - ★Java (a Spring Boot + Lombok repo, 2026-10-15): of undeclared call names used >= 3 times ~54% were record components, ~1.4% Lombok, the rest JDK calls. ⇒ `.java` files of `to`: a record component counts only if the evidence file names the record type (`ev`); `getX`/`isX`/`setX` need field `x` + @Getter/@Data/@Value (@Setter/@Data) on class or field; `builder` needs @Builder; Lombok too needs the evidence file to name the class, and `AccessLevel.NONE` turns the accessor off. ⚠Without the type-name check `list.size()` / `obj.getId()` / `WebClient.builder()` pass on any record / @Data / @Builder class.
- **Any `sidereus/structure_lang_*.py` becomes a language plug-in** (2026-10-05, `structure_plug.plug_load`, filename glob).
  - Cause: plug-ins are found by name, not by an import list, and imported while `structure_scan` is still loading.
  - ⇒ Name helper modules anything else; a plug-in imports only modules earlier than `structure_scan`. A failing one is skipped with a warning.
  - ⚠Never name a non-plug-in file `structure_lang_<x>.py`; it is executed at import and its exts join `STRUCT_EXTS`.
- **C/C++ `#if` parses only the first branch** (2026-10-05, `structure_lang_c`).
  - Cause: both branches of `#if/#else` often open the same block (`{` twice, one `}`), so reading both breaks brace depth.
  - ⇒ The first branch is kept (`#if 0` / `#if false` hand it to the next), the other branches are blanked (lines kept).
  - ⚠Declarations only in an `#else` branch are missing from the treemap — expected, not a bug.
- **Kotlin `enum class X` became a node named «class»** (2026-10-05, `structure_lang._JAVA_CLSDECL`/`_java_scan`).
  - Cause: the keyword alternation matched `enum` and took `class` as the name — ★9 duplicate «class» nodes in 3 files of one Android repo. The method scan also dropped newlines (`Marker\ndata` → one token) and took the first decl in a `;`-less Kotlin header.
  - ⇒ Lookahead `(?!(?:class|interface)\b)` so the match lands on `class X` (the `enum\s+$` prefix check sets the kind); newline adds a space to the scan buffer; the last decl before `{` owns the body.
  - ⚠Do not add `enum`/`data`/`annotation` etc. as decl keywords — they are modifiers before `class`.
- **A settings row that has no effect in the current state is disabled, not hidden** (2026-10-05, `web/js/90-settings.js` `cfgSet(..., dis)`).
  - Cause: «Also when this tab is visible» with session alerts off, and the target burn rate outside «Auto», were clickable and did nothing.
  - ⇒ Pass the reason as `dis`: the row dims, its controls are disabled, the reason is the title. Internal-path rows (hook folder, port, compact history) live under the «Advanced» fold (`sidereus.cfgadv`).
  - ⚠Never drop the pref key when moving or relabelling a row — only layout and labels change.
- ★**81h `mmdSeqSvg` object 4th arg is for the 84k arch flows only** (2026-10-02; 84k passes `{tag: 1, fit: 0.75}`).
  - Cause: the same renderer draws the markdown preview (81e); md preview output is pinned by tests.
  - ⇒ Extra looks are opt-in by an object 4th argument; no tag and `tag = 1` stay byte-identical.
  - ⚠Never pass the object from 81e — md preview must stay byte-identical.
- ★**81e `mmdSvg(g, L, key, tag)` 4th arg is for the 84j arch diagram only** (2026-10-02: edges in `<g class=mmdfe data-c>`, nodes `data-p` / `<title>`, `box3d` subgraphs, shape `comp`).
  - Cause: the md preview draws with the same function; its output is pinned (FLOW/ARCH sha256 in `tests/test_structure_mermaid_js.py`).
  - ⇒ Hooks only when `tag` is truthy. `L.edges` carry no model index, so `data-c` is found by the edge's from/to — callers make one edge per pair.
  - ⚠Never pass `tag` from `mmdBlock`. ⚠Path and label are wrapped separately (same `data-c`) so labels stay above lines and nodes.
  - ⚠`box3d` subgraphs draw the title at the left: `mmdLayout` moves the title wall (`tr`) to match — a centred wall let lines cross the drawn name.
  - Tag mode places labels itself (`mmdFlPlace`, not 81g's on-line pill): beside a run, clear of nodes/titles/labels/bounds; none free = number badge + legend column (viewBox widened).
- ★**md split scroll anchors are separate `.mdln` markers, not attributes** (2026-09-29, `web/js/00-core.js` `md(src, doc, ln)`). Tests pin `md(text,1)` output byte-for-byte (`<h1>…</h1>`), so a `data-ln` on block tags broke them. ⇒ Only the split view passes `ln`; each block gets a zero-height `<i class=mdln data-ln=N>` before it. ⚠Never add attributes to md()'s block tags; chat and doc output must stay identical.
- ★**md split scroll stopped at 0.969** (2026-09-29, `web/js/81c-structure-fold.js` `strMdPairs`). An anchor below a pane's max scrollTop is unreachable, and it made the `end >= last` check drop the scroll-end pair. ⇒ Compute `end` first; keep only anchors strictly below it on both panes. ⚠Always append the end pair, or bottom never maps to bottom.
- ★**Structure «tests only» filter left the screen stuck empty** (2026-09-25; in a project with no tests the code-filter select itself was not drawn, so there was no way back). ⇒ Code filter `#strtf` and colour `#strax` (web/js/80-structure.js:443,449) live in `head()` (80-structure.js:454), which draws every state: loading/error/empty. ⚠Even when adding a new structure state branch, never draw outside `head()` — the select goes missing.
- Code filter `tests=0|1|only` is **server mode** (`_struct_tmode`, structure_scan.py:61) — the server applies area sums and the cell cap. It is part of the cache key (`STRUCT_RULES_VER`+`_struct_tmode`, structure_snap.py:51). ⚠Do not revert to client-only filtering — it disagrees with the server aggregates.
- ★**Right after reconnect the structure tab did not switch to another session** (2026-09-25; `bootView` drew before the first `/api/state` (SESS=[]) and nothing redrew it afterwards). ⇒ `poll()` (95-poll.js:23) redraws the structure tab only when `strSessKey() !== strSessSig` (80-structure.js:248,249,419). ⚠Never redraw on every poll without the session-key comparison — open cells and scroll flicker.
- ★**Structure tab `cat-file --batch` feeds stdin from a thread and is killed at the deadline (`STRUCT_GIT_TIMEOUT`×3)** (2026-09-25 review). Writing every sha before reading filled git's stdout pipe and the write blocked forever (★measured: 18k sha/738KB blocked · 3k passed) — it holds a git slot (cap 3), so 3 of them starve all viewer git. ⇒ A failed git step (slot wait, deadline) is not put in `_struct_blob_cache`; a result with a failed step is returned as `incomplete` for this response only and not written to the memory/disk «out» cache (in a quiet repo the key does not change, so incomplete history survived restarts). Test `tests/test_structure_git_batch.py`.
- ★**«source / test» pair in the structure panel** (2026-09-23).
  - `/api/structure/pair?path=&file=` → `structure_pair()` (`sidereus/structure.py`) · pure matcher `_struct_pair_match()` (`sidereus/structure_pairing.py`). Rules by strength: `mirror` (`src/main`↔`src/test`) · `dir` (same/child folder·`__tests__`) · `name` (`test_x`·`x_test`·`.test/.spec`·`FooTest(s)/IT`) · `ref` only when no name match exists (top 5 · dimmed on screen). `ref` is **real references only**: py = import statements + real calls like `sidereus("usage")` after `tokenize` strips strings and comments · java/kt = a used `import <FQCN>` or a same-package word use outside comments/strings · js/ts = resolved import/require paths (`./`·`@/`).
  - ⚠Do not revert to loose `\bName\b`/quote matching — a `"usage"` inside a string was picked as a pair (`_struct_pair_targets`).
  - ★**ref order = use count** (2026-09-24). Cause: ordering only by via (import>package) put a config test (2 uses) at the top for a controller in a Spring repo.
    - ⇒ `_struct_pair_targets(..., uses)` counts the names a reference binds (java class name · py import/alias·`S = sidereus("x")` · js import name) in the code minus import statements. Sort by `-uses` (ties keep the old order), then top 5. Screen «reference · import · N times».
    - ⚠The count only orders; it does not decide pairing — a reference with 0 uses stays.
  - Screen: `.strpr` list under the function-cell panel (`strPairBox`) → click opens the split popup `.strsp` (main code left · test right, `strPop.pair`). Independent of the test toggle.
  - ⚠Path confinement is the same `_struct_src_root`·`_struct_src_rel` as `/api/structure/src` — never remove it. ⚠Current tree only (not past snapshots) · 400-line cap per column (`STRUCT_SRC_MAX_LINES`). ⚠`.go` is outside `STRUCT_EXTS`, so it has rules but never appears in the list.
  - ★Measured: `sidereus/usage.py`→`tests/test_quota_who.py` (ref) · `…/src/main/…Controller.java`→`…/src/test/…ControllerTest.java` (mirror) · `x.ts`→`x.test.ts` (dir). A Spring repo's main java 1,146 = mirror 122 · name 113 · ref 690 · none 221; 10 sampled refs, 0 false positives (all really used in code — but they are «tests that use it», not «that class's dedicated test»). ref fallback = ~55ms per source (cap 1,500 tests).
- ★**The structure tab shows code and changes** (2026-09-22).
  - New API `/api/structure/src` (`structure_src()`). The point in time is read as-is from git `show <rev>:<file>` · tar/bak · current file, in that order; **if unavailable it says so: current file + `exact:false` + screen text** (never pretend). Cap 400 lines (★measured 588-line function) · disk cache only for immutable points (`kind="src"`).
  - ⛔**Never remove path confinement — without it this is arbitrary file read.** ① allow-list is `_struct_warm_targets()` only ② reject `..`·absolute paths·unknown extensions ③ final `realpath` check that it is inside the project (symlinks are caught here). ★Measured rejections: `../../etc/passwd` · `/etc/passwd` · `path=/etc` · `path=/Users/<user>/<workspace>`.
  - The body is in **popup `#spop`**, not the panel (same convention as `#dpop`: `body.spop` · ✕ · Esc). It is outside `.wrap`, so the 2.5 s poll cannot erase it. ⚠While the popup is up the canvas width reads 0, so **redraw on close**.
  - ⚠Without `min-height` on `.strpn`, at 400px the list **collapses to 21px** and disappears (★measured content 133px). The diff table is the same `table.sbs.uni` as the work log (`strEdRows` uses the same algorithm as `editRows` :13135, 600-row cap — **never fix only one side**).
- ★**Structure code/changes open in a real window, not a modal** (2026-09-22).
  - ⇒ `strPopOpen` opens it with `window.open` and copies the main document's `<style>` in (there is no separate CSS file). Drawing targets the document chosen by `strPopDoc()`.
  - ⚠If the popup is blocked it falls back to the old overlay `#spop` — do not delete that markup.
- ★**Cells changed at this point get a blue border** (2026-09-22). Gold stays «new cell» as before.
  - ⇒ When `strLastOf(a,f) === strSi(a)`, cell border `#5aa9e6`; the child list gets a «changed at this point» badge (`.strfl u.chg`).
- ★**The treemap was one colour and clicking a cell meant nothing** (2026-09-22).
  Cause: the only colour axis was churn, and **0 edits was 73.1% in Sidereus · 87.5% in repo-B · 83.2% in repo-A**. One of the largest cells, «+N more» (area cap 60), had a dead click.
  ⇒ ① the server attaches `last` (snapshot index of last change) per function and the default axis is **«recent change»** (`STR_AGE` = ratio **relative** to the previous snapshot · colour ramp stays `STR_COL`, legend text follows the axis) ② group-cell click = drill into that area + `?full=1` (`STRUCT_FULL_FNS`=400) ③ function-cell click = metadata panel (`file:line`·line count·churn·last change·line-count sparkline).
  ★Measured by canvas pixels, darkest colour **33.8% (edit count) → 19.4% (recent change)** · «Other» drill-down 60 cells → 227 (0 groups). ⚠Do not lift the cap on the full screen — repo-A 13,485 functions = 22MB response.
  ⚠**Never put source bodies in the panel** (rule 1: metadata only). ⚠Area drill-down was kept and only function cells moved to the panel — merging them removes the way to see a large area large.
- ★**The structure cache was memory-only, so every restart was fully cold — disk cache + idle warm-up** (2026-09-22).
  ⇒ `~/.mailbox-mcp/struct-cache/*.json.gz` (temp file + `os.replace`). Three kinds: immutable snapshots (`blob` = git sha·tar·bak) · per-file parse of the current tree (`fcache`) · final response (`out`). Cap 200MB/30 days; cleanup only in the warm-up thread. `_struct_warm_loop()` warms the union of session `cwd`+`repos` **one at a time** and adds `warm` to the response.
  ⚠Mix the versions (`STRUCT_DISK_VER`·`STRUCT_RULES_VER`) **into the filename hash** — with only an in-body `rv` check, two versions overwrite the same file in turn and neither hits. ⚠Exclude `/api/state`·`/api/live` from warm-up «idle» (they poll every 2.5 s, so idle would never come). ⚠Read failures are silently ignored and recomputed.
  ★Measured cold → new process: Sidereus 2.49→0.01s · repo-B 4.50→0.05s · repo-A 4.14→0.05s. `total`, top areas and churn distribution all identical. Editing one file re-parses **only that 1 file** (0.12s). Cache for 6 projects 4.4MB.
- ★**Vendor name lists and tests swamped the structure — split by content and added `?tests=`** (2026-09-22).
  Cause: the name/version rule caught only `ace-builds-1.2.6`, so repo-A's `template/js` 18,434 lines (jindo·FusionCharts·dhtmlX) rose to the top areas; in repo-B `src/test` 111,052 lines beat `src/main` 96,315 for 1st and 2nd.
  ⇒ `_struct_vendor_blob()` = **content check** (longest line 500 · mean 200 · over 4,000 lines · licence header in the first 40 lines) + `_struct_is_test()` = path/filename. `/api/structure?tests=0|1` (**default 0**); with `tests=1` areas carry `test:true`. Every snap has `excluded{vendor,vendorLines,test,testLines}`.
  ⚠The content check is **js/ts family only** — generated JSP and large Java are the real code. Keep the name/path rules alongside it.
  ⚠When rules change, bump `STRUCT_RULES_VER` — it is in the cache key (with `tests`). ★Measured tests=0: repo-A `template/js` 18,434→4,714 (2.2%) · `test/*` gone from repo-B's top · Sidereus 19,574 unchanged.
- ★**The structure parser missed the «main language» — added `.java`·`.jsp`, dropped static vendor js** (2026-09-22).
  Cause: extensions were only `.py/.js/.ts/.tsx/.jsx`, so repo-B's java 1,675 · repo-A's java 1,352 + jsp 400 were dropped wholesale. ★repo-A's 562,705 lines were almost all vendor js like `ace-builds`, hence churn 0 for 99.5% (87.2% after the fix).
  ⇒ ① `_java_scan()` = brace-depth scanner (names are **`Class.method`** · on breakage only that file is dropped and counted in `snap.skipped`) ② `.jsp/.jspf/.tag` = **one file = one cell** ③ `STRUCT_VENDOR_VER` (`<name>-<version>` directories) excludes 1,409 js files (36.7MB).
  ⚠Vendor exclusion is **js family only** — `lib` in `.java` is a package name, and `src/lib`·`src/assets` are app code (14 repo-B `frontend/src/lib/*.ts` files were lost).
  ⚠Do not revert `STRUCT_DIR_MAX_SHARE` to 0.7 — `src/main/java/com/<company>/…` collapses into two cells, `main` and `test`. ★Cold: Sidereus 2.4s · repo-B 6.9s · repo-A 4.6s (minutes before vendor exclusion).
- ★**Structure project chips select «one only»** (2026-09-22).
  ⇒ Chip `onclick` **replaces** rather than toggles (`strOn = [p]`). `strOn` is still an array, but holds one.
  ⚠The merged path in `strBuild()` (`merged:true`) is **not used now** — keep it (for when multi-select is needed).
- ★**The structure treemap is a single `<canvas>` — do not revert to DOM cells** (2026-09-22).
  Cause: 380 cells (★measured in Sidereus) and playback redraws everything every 0.6 s — creating elements runs layout that many times. ★canvas measured frame median 0.30ms · max 0.70ms (380 cells · dpr 2).
  ⇒ `paintStruct` (structure tab = `mainView 'struct'`) emits only the shell as HTML; `strSquarify` (own implementation · no library) → `strLayout` (outer = area · inner = function) → `strDraw` draws cells. Hover uses a **reverse coordinate index** over `strRects` (scan from the end so function cells are on top).
  ⚠If `area.more` (functions omitted by the 60 cap) is not drawn as a «+N more» cell, the area sum disagrees with `area.lines` · ⚠`snap.partial` is drawn with a dashed border (otherwise a step reads as «growth») · ⚠the target list uses **only `cwd` paths** from `SESS` — conversation content never goes on this screen.
  ⚠`/api/structure` is 2–4 s cold — responses go in `strCache[path]` and the slider/playback read only the cache (do not hang it on the poll).
- ★**Never hard-code the canvas height — give it all remaining vertical space** (2026-09-22).
  Cause: fixed `STR_H = 470` drew the canvas at 1696×**470** and left 710px idle below it (★measured feed 1180px).
  ⇒ The structure tab is a vertical flex `.strtab` — header, two chip rows, exclusion line, legend, slider are fixed; only `.strwrap` is `flex:1` (floor 320px · **no cap**). `strDraw` reads `clientHeight` every render and a `ResizeObserver` (coalesced into one rAF) redraws. ★Measured viewport 600/900/1200 → 318/544/844px (= feed − fixed 181 − border 2).
  ⚠In a hidden tab `clientHeight` is 0 — **return without drawing** (drawing at 0 collapses the canvas). ⚠CSS height and `cv.height` are separate (`cv.height = H*dpr` + `setTransform(dpr…)`; at dpr 2, 856×844 → 1712×1688).
  ⚠The «Include tests» toggle value is **part of the `strCache` key** (`path\n0|1`) — without it, toggling shows the old result. Excluded counts show `snap.excluded` as one header line (omitted for old servers without the key).
- ★**A session's repos are already in `sessions[].repos` — never collect only `cwd`** (2026-09-22).
  ⚠An earlier note saying «`repos` is empty» was **wrong** (★measured: all 4 sessions had 1–2 each). Check `curl -s .../api/state` yourself before changing it.
  ⇒ Two chip rows: top = session (+all) · bottom = union of `cwd`+`repos` (multi-toggle). With several on, `strBuild()` merges into **3 levels** (project → area → function); with one, the response object is used as-is, **2 levels unchanged** (no regression — 17,268 cell coordinates compared, 0 mismatches).
  ⚠Snapshot times differ per project — the time axis is the **union**, each project shows «latest at or before that time» (step-wise). Before a project's first snapshot, **omit it rather than draw 0** (it did not exist yet).
  ⚠Cold is 1.5–4 s per project — call `strFetch` **in parallel** and draw as each arrives (waiting for all leaves the screen blank that long).
- ★**Cutting time-series sources to «latest N» makes churn all 0 — sample evenly along the time axis** (2026-09-22).
  Cause: the 10 `backup/*.tar.gz` all covered 70 minutes of one day (08:11~09:21). Drawing 20 days from them gave churn 0 for 356 of 365 functions (97.5%).
  ⇒ `backup/old-baks/*.bak-*` (37 plain files · 9/02~) joined the candidates and `_struct_spread()` picks 20 by **farthest-point sampling**. ★Result: churn 0 for 66.3% · max 8. Labelled ones (`bak-rooms-073308`) have no date in the name, so mtime is used.
  ⚠`old-baks` hold only `chat_server.py`, so `total` at that point is not the whole project — told apart by snap `partial`·`files` (threshold **90% of the current tree's file count**).
  ⚠Do not use «closest to evenly spaced target times» — targets in empty stretches collapse onto one point and duplicate, and filling gaps from the front ends up picking only the dense stretch. ⚠`_struct_label` adds the year when years differ (otherwise multi-year commits read jumbled, `9/25 → 5/24`).
- ★**Drill-down (`full=1`) never folds `rest` into «Other N files»** (2026-10-05: inside sidereus the «Other 90 files» cell, 6272 lines, did nothing on click).
  - Cause: `strClick` drills only once (`strFull` already 1), and `_struct_rest` still folded past 40 files, so the cell had no deeper level.
  - ⇒ `_struct_group` passes `len(tail)` as the rest cap when `maxf > STRUCT_MAX_FNS`. ★sidereus: 41 rest entries → 130, 9.5KB → 55KB per area (`tests/test_structure_rest.py`).
  - ⚠Keep the 40-file cap on the full screen — every area would carry every file.
- ★**Drill-down list starts folded, inside the map** (2026-10-05: the open list's 3/5 share cut the map 499 → 188px; a folded card as its own row still cost 73px). ⇒ `.strpnC` is rendered inside `.strwrap` on the zoomed area's 20px header band (80-structure.js) — map 575/535/531px before and after at 900/1100/1440; «Show list» (`sidereus.strpnl`). ⚠The `:has(.strpnL)` split rule must skip `.strpnC`, or the folded panel still takes 3/5.
- **«Architecture» request done = a map with a new commit, not «a map exists»** (84j `archSentDone`).
  - Cause: a request sent from a «stale» map already has modules on screen; «has modules» would close it at once.
  - ⇒ `ARCH.sent.base` keeps the commit on screen at send ('' when empty); done = modules + commit ≠ base. The completion notice is `note()`.
  - ⚠Not `toast(c)`: card toasts are server bell history and their click posts a read key to `/api/cards/read`.
- **arch-map runs from a project with its own pipelines leave no `plrun`** (`sidereus/arch_map.py` `runs`, `48h-pipeline-sidereus.js`).
  - Cause: `hooks/pl_flow.py:137` never borrows another project's pipelines when the cwd has its own, so arch-map (defined in the Sidereus repo) gets no runs.json entry.
  - ⇒ Sidereus derives the run from live `[pl:arch-map/…]` stage tags (sub · plm · Agent targ) + the pending store dir → state `archRun`.
  - ⚠Do not «fix» it by writing pipeline files into the user's project.
- **A finished arch-map run kept showing «Analysing · 4/4 · Verify»** (`sidereus/arch_map.py` `_finished`).
  - Cause: the orchestrating session stays busy with other work, so its signs (closed run's plm, lingering labels) plus the 180s carry-over kept the run alive; nothing looked at the gate result.
  - ⇒ A run ends once the target store has a verify.json newer than every start sign of the run, and the run record closed after it or no tagged subagent / Agent call is live. The carry-over skips such runs.
  - ⚠Do not compare against the fallback t0 (`now` on first sight): only real start signs (plrun t0, sub age, pending plan.json, carried t0) may keep a run alive past a result.
- **Issues window `sidereus_checks` runs its events through the opener** (`web/js/84l-structure-arch-checks.js` `ARCH_CW_JS` → `archChkWinEv`).
  - Cause: the window is about:blank written by the viewer; a row click opens the code popup with `window.open`, which needs the clicked window's user activation.
  - ⇒ A script inside the window forwards click/change/keydown to `opener.archChkWinEv(e, window)`; the handler acts only when `ARCH_CW.w === w`. Repaint is `innerHTML`, so `archChkWinPaint` saves and restores the list `scrollTop`.
  - ⚠Do not attach parent-realm listeners to the window's document instead — the code popup can be blocked. ⚠Any new repaint path must keep the scroll restore.
- **Deleted worktrees left project chips behind** (Structure · Pipelines · mail-watch lists all read `80 strProjList`).
  - Cause: sessions keep their `cwd`/`repos` after the folder is removed, so every old worktree stayed a chip.
  - ⇒ `/api/state` `projGone` (`sidereus/state.py` `proj_gone`, isdir memo per path `PROJ_DIR_TTL_S` 30 s) → `PROJ_GONE`; `strProjList`/`strDefProj` skip those paths, a selected gone project re-picks the default (Structure) or the first listed one (Pipelines).
  - ⚠Filter chips only — session rows, timeline and history keep the gone folder's sessions.
