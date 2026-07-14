# Changelog & Reference

Version history and reference details for the `xmind` skill. The main skill
description lives in [`SKILL.md`](SKILL.md) — that file is loaded into context
on every trigger and covers what the skill does, design rationale, quick
start, dict schema, output format reference, and limitations. This file holds
the *historical* changelog and *static* reference (install, project layout)
that an LLM rarely needs at trigger time but a human reader may consult.

## v0.7.1 Fixes (CLI dispatch + md relationship rendering)

Two fixes found while testing the skill on a real user file (`公开 仿真资源管理 - 副本.xmind`, 2 sheets / 186 topics / 1 note / 1 relationship):

1. **CLI console-script was broken (critical).** `main(argv=None)` did `if not argv: parser.print_help(); return 0` — so the installed `xmind-tool` command printed help and exited 0 for *every* invocation (`xmind-tool info <file>`, `xmind-tool read ...`, etc.). The bug was invisible to tests because `test_cli._run_cli` passes `argv` explicitly as a list, never exercising the `argv=None` path the console-script entry point uses. Fix: when `argv is None`, default to `sys.argv[1:]`. Added `TestCliDispatchFromSysArgv` (2 tests) that monkeypatch `sys.argv` and call `main()` with no args — verified RED against the old behavior, GREEN after the fix.

2. **md export now renders `relationships` as a read-only footnote.** Each sheet's relationships are rendered as a `## 关联` section at the end of the sheet, with endpoints as `` `端点A` ↔ `端点B`（标题） `` (endpoint id resolved to title via a pre-pass `id → title` map; falls back to id prefix, never raw uuid). md→xmind **drops** this section by design — relationships belong to the JSON channel (`relationships` on the sheet dict), not the md channel. This matches the existing asymmetric design (md = lossy human-facing artifact; JSON = lossless LLM/round-trip channel). Documented in SKILL.md Output Format Reference + Markdown Import Syntax table.

Verification: 119 tests pass (117 + 2 new CLI dispatch), 3 skipped (unchanged). Real-file round-trip on `公开仿真资源管理 - 副本.xmind`: sheets/topics/notes/relationships all 1:1 through read→write→read; relationship id/end1Id/end2Id/controlPoints all preserved.

## v0.7.0 Fixes (real-world robustness audit → lossless parse)

A robustness audit on **110 real XMind Zen files** (Psyduck 82 + CS-Xmind-Note 28: CS/database/distributed-system/Golang/Linux tutorials) found that all 110 passed the no-exception bar and preserved topic count on round-trip — **but the reader silently dropped several features real files use**. A deep semantic audit (key census over every topic/sheet in raw `content.json`) + two parallel subagent probes (image/boundaries, relationships/legend/rich-notes) grounded each fix in the exact on-disk shape. 17 RED tests → all green; final verification: **zero feature-drop across all 110 files** (10469 topics, 616 images, 55 relationships, 18 boundaries, 109 extensions, 3579 styles, 71 summaries all preserved 1:1 through read→write→read).

- **`image` dropped by reader** — 616 image-bearing topics across 80 files; `image = {src:"xap:resources/<hash>.png", width, height, align?}`. Reader never read it (writer already passed it through, so the round-trip was silently halved). Fixed: reader pass-through.
- **`boundaries` dropped** — 21 topics carry visual grouping boxes `[{id, title, range:"(i,j)", style?}]`. Fixed: reader + writer pass-through; range preserved as string.
- **`relationships` dropped** — 55 cross-tree edges in 14 sheets `[{id, end1Id, end2Id, title?, controlPoints?}]`. These are *semantic* (A→B links), not layout. Fixed: sheet-level pass-through in reader + writer.
- **`id` not preserved → relationships dangle** — writer regenerated every topic id, so even preserving relationships left `end1Id`/`end2Id` pointing at nothing. Fixed: writer uses `topic.get("id") or new_id()`, preserving original ids on round-trip. Verified end-to-end: relationships survive round-trip with valid endpoints.
- **`extensions` dropped** — 109 topics carry opaque addon blobs. Fixed: pass-through.
- **Sheet-level keys dropped** — `legend` (9 sheets), `class`, `style`, `topicPositioning` on sheets were lost. Fixed: sheet-level pass-through.
- **Layout keys dropped** — `customWidth` (2078), `width` (207), `position` (34). Fixed: pass-through.
- **Summary topic with empty title + image was skipped** — `map.xmind` had a summary topic with `title=""` but an embedded image; the "pure reference" guard (meant to skip `{id,range,topicId}` stubs) was too aggressive and dropped it. Fixed: guard now checks for *any* content (image/style/labels/...), not just title. This recovered the 616th image.
- **md/csv/opml confirmed clean** — new pass-through fields do *not* leak into human-facing exports (no raw uuids, no `xap:resources`, no `boundaries` text in md/csv); they live only in the JSON/YAML channel, consistent with the asymmetric design.

Audit scripts (`robustness_scan.py`, `deep_audit.py`, `zero_loss.py`) are reproducible artifacts; the 110-file corpus was cloned from `SmartKeyerror/Psyduck` and `SSHeRun/CS-Xmind-Note`.

## v0.6.1 Fixes (md↔xmind coverage audit, TDD)

A real-file audit (recursive scan of all topic keys in `公开 仿真资源管理.xmind`) + 8 RED tests found and fixed 4 gaps:

- **Inline markup leakage** — `**bold**` / `` `code` `` / `*italic*` in headings leaked the marker characters verbatim into the topic title (XMind then showed literal asterisks/backticks). Fixed: `_strip_inline_markup` strips heading text to plain (XMind expresses bold via `style.properties.fo:font-weight`, not text symbols).
- **Bullet list silently dropped** — `- item` lines were skipped entirely (data loss, no error). Fixed: `-`/`*`/`+` list items become attached children of the current topic, with indentation (4 spaces/level) nesting deeper.
- **Callout was one-way** — reader read `callout` and md-rendered `**Callout:**`, but the parser had no reverse branch, so the line was lost on md→xmind. Fixed: `**Callout:** text` now parses to `topic.callout`; writer also routes `callout` into `children.callout` (XMind Zen's real location) instead of a top-level field.
- **`style` dropped by reader/writer** — real files store node bold via `topic.style.properties.fo:font-weight`; reader discarded `style` entirely, so even the JSON channel lost it. Fixed: reader preserves `style`; writer passes it through. Verified lossless on the real file: 11 bold topics survive xmind→JSON→xmind→read (11→11).

## v0.6 New Capabilities

- **Default theme injection** — Zen writes now inject a built-in colorful theme (`assets/default_theme.json`, extracted from a real XMind file) so maps open looking polished, not plain black-on-white. Theme covers: 6-color branch palette, NeverMind font, sized/weighted central/main/sub topics. Pass `theme=USE_DEFAULT_THEME` (default), a custom theme dict, or `None` (no theme). CLI: `--theme <file.json>` / `--no-theme`.

## v0.5.1 Fixes (roundtrip-tested on real .xmind)

- **CSV Excel-encoding fix** — `xmind_to_csv` now writes UTF-8 with BOM (`utf-8-sig`); previously Excel decoded no-BOM UTF-8 as GBK and showed garbled Chinese. CLI `read --format csv` to stdout stays BOM-free (BOM only in files).
- **Markdown-import detached/summary note bug** — `[游离]`/`[概要]` topics' `note`/`labels`/`makers`/`link` were mis-attached to the parent node (the parser didn't push them onto the parse stack). Fixed: detached/summary nodes now receive their own metadata. Caught by a stress roundtrip on a fixture containing detached topics with notes.

## v0.5 New Capabilities

- **Legacy (XMind 8) write** — `write_xmind(sheets, path, format="legacy")` emits `content.xml` + `META-INF/manifest.xml`; available via `xmind-tool write ... --format legacy` and `convert ... --format legacy`
- **Session memory** — `xmind-tool read <file> --format md --session <id>` caches to `.xmind-cache/<session>/` next to the source (cwd fallback on read-only); `xmind-tool memory <file> --session <id>` retrieves it. Defeats long-context compression: parse once, resume by id

## v0.3 New Capabilities

- **CSV export** — `xmind_to_csv()` flattens mind map to a spreadsheet-friendly table
- **OPML export** — `xmind_to_opml()` produces OPML 2.0 with full hierarchy + custom metadata attrs
- Both available via `xmind-tool read --format csv|opml` and `xmind-tool convert foo.xmind -o foo.csv|opml`

## v0.2 Capabilities (still present)

- **Markdown → .xmind import** — parse a `.md` document into a multi-sheet mind map
- **Styles/manifest pass-through** — `read_xmind_full` + `write_xmind_full` preserve `styles.json` and `manifest.json` byte-for-byte
- **Globally installed `xmind-tool` command** — `pip install -e .` puts the CLI on PATH

## Installation

```bash
pip install xmindparser pyyaml
```

For the global CLI command:

```bash
cd ~/.cc-switch/skills/xmind
pip install -e .
# now from any directory:
xmind-tool --help
```

(On Windows, ensure `C:\Users\<you>\AppData\Roaming\Python\Python314\Scripts` is on PATH.)

## Project Structure

```
xmind/
├── xmind_tool/          # the package
│   ├── reader.py        # xmindparser wrapper + read_xmind_full
│   ├── writer.py        # Zen (zipfile+json) + Legacy (content.xml) writers + theme injection
│   ├── convert.py       # format conversion (incl. md → xmind, csv, opml)
│   ├── memory.py        # session memory (.xmind-cache, cwd fallback) [v0.5]
│   └── cli.py           # CLI entry
├── assets/
│   └── default_theme.json  # built-in colorful theme [v0.6]
├── tests/               # 119 unittest cases
│   ├── test_reader.py   (4)   # +style.properties [v0.6.1]
│   ├── test_writer.py   (7)   # +style pass-through [v0.6.1]
│   ├── test_legacy_writer.py (5)   [v0.5]
│   ├── test_convert.py  (6)
│   ├── test_csv_opml.py (12)   [v0.3, +BOM v0.5.1]
│   ├── test_markdown_reverse.py  (15)  # +inline-markup/bullet/callout [v0.6.1]
│   ├── test_robustness.py  (17)  # +image/boundary/relationship/id/extensions/layout +real-file [v0.7.0]
│   ├── test_memory.py   (9)   [v0.5]
│   ├── test_theme.py    (5)   [v0.6]
│   ├── test_styles.py   (5)           [v0.2]
│   ├── test_summary.py  (14)
│   └── test_cli.py      (19)
├── samples/             # demo.xmind fixture
├── assets/
│   └── default_theme.json  # built-in colorful theme [v0.6]
├── pyproject.toml       # install + entry point
└── README.md
```
