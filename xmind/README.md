# xmind_tool

Lightweight `.xmind` read/write/convert toolkit. See `SKILL.md` for the full skill description (including the **Design Rationale** on why md→xmind is the headline feature, why xmind→md is human-facing not LLM-facing, and why md round-trip is lossy).

## Install

```bash
cd ~/.cc-switch/skills/xmind
pip install -e .
```

After install, three ways to invoke the CLI:

```bash
# 1. Direct command (works in native Windows cmd / PowerShell)
xmind-tool --help
xmind-tool info brain.xmind
xmind-tool write structure.json --output out.xmind --format legacy   # XMind 8

# 2. Via Python module (always works, no PATH needed)
python -m xmind_tool.cli --help
python -m xmind_tool.cli info brain.xmind

# 3. Via full exe path
"C:\Users\Breeze\AppData\Roaming\Python\Python314\Scripts\xmind-tool.exe" --help
```

**Note on Git Bash users:** the `xmind-tool.exe` shim has known arg-passing issues when invoked from Git Bash (mingw). Use `python -m xmind_tool.cli` instead — it works from any shell.

## Run all tests

```bash
python -m unittest discover -v tests
```

122 tests cover: reader (4) + writer (8) + legacy_writer (5) + convert (6) + markdown-reverse (16) + robustness (17) + styles (5) + csv/opml (12) + memory (9) + theme (5) + summary (14) + CLI (21).

## End-to-end smoke

```bash
# Legacy write (XMind 8)
python -m xmind_tool.cli write notes.md --output mymap_legacy.xmind --format legacy

# Theme control (v0.6) — default injects a colorful theme; --no-theme for plain; --theme <file> for custom
python -m xmind_tool.cli write notes.md --output mymap.xmind                  # default theme
python -m xmind_tool.cli write notes.md --output mymap.xmind --no-theme       # plain black-on-white
python -m xmind_tool.cli write notes.md --output mymap.xmind --theme my.json  # custom theme

# Session memory (breakpoint resume)
python -m xmind_tool.cli read brain.xmind --format md --session my-sess
python -m xmind_tool.cli memory brain.xmind --session my-sess    # retrieve later

python -m xmind_tool.cli convert notes.md --output mymap.xmind
python -m xmind_tool.cli info mymap.xmind
python -m xmind_tool.cli read mymap.xmind --format md
python -m xmind_tool.cli read mymap.xmind --format csv       # v0.3 (now BOM-safe for Excel)
python -m xmind_tool.cli read mymap.xmind --format opml     # v0.3
```

## Dependencies

- `xmindparser` (read both XMind formats)
- `pyyaml` (yaml I/O)
- Python stdlib `zipfile` + `json` (write), `csv` (CSV export), `xml.etree` (Legacy write + OPML export)

No image/attachment libraries — out of scope.

## v0.7.0 highlights — real-world robustness audit → lossless parse

Audited **110 real XMind Zen files** (Psyduck 82 + CS-Xmind-Note 28: CS/database/distributed-system/Golang/Linux tutorials). All passed the no-exception bar, **but the reader silently dropped features real files use**. Deep semantic audit (key census over every topic/sheet) + two parallel subagent probes grounded each fix in the exact on-disk shape. 17 TDD tests; final verification: **zero feature-drop across all 110 files** on read→write→read.

- **`image`** (616 topics across 80 files; `{src:"xap:resources/<hash>.png", width, height, align?}`) — reader never read it.
- **`boundaries`** (21 topics; `[{id, title, range:"(i,j)", style?}]`) — visual grouping boxes.
- **`relationships`** (55 cross-tree edges in 14 sheets; `[{id, end1Id, end2Id, title?}]`) — semantic A→B links.
- **`id` preservation** — writer used to regenerate every topic id, so relationships' `end1Id`/`end2Id` dangled. Now preserved on round-trip → relationships survive with valid endpoints.
- **`extensions`** (109 topics), **sheet-level `legend`/`class`/`style`/`topicPositioning`**, **layout `customWidth`/`width`/`position`** — all now pass-through.
- **Summary topic with empty title + image was skipped** — `map.xmind` had a summary topic (`title=""` + image) that an over-aggressive "pure reference" guard dropped. Guard now checks for *any* content, recovering the 616th image.
- **md/csv/opml stay clean** — new pass-through fields live only in the JSON/YAML channel; no raw uuids/`xap:resources`/`boundaries` leak into human-facing exports.

Audit scripts (`robustness_scan.py`, `deep_audit.py`, `zero_loss.py`) are reproducible. Per-feature totals on the 110-file corpus, original → after round-trip (all +0): topics 10469, images 616, boundaries 18, relationships 55, extensions 109, styles 3579, summaries 71, detached 26, notes 12, links 3.

## v0.6.1 highlights

md↔xmind coverage audit (recursive real-file scan + 8 TDD tests) found and fixed 4 gaps:

- **Inline markup leakage** — `**bold**` / `` `code` `` / `*italic*` in headings no longer leak their marker chars into the topic title; stripped to plain text (XMind expresses bold via `style.properties.fo:font-weight`, not text symbols).
- **Bullet list silently dropped** — `- item` / `* item` / `+ item` now become attached children of the current topic, with indentation (4 spaces/level) nesting deeper (previously: silently skipped, data loss).
- **Callout was one-way** — `**Callout:** text` now parses back to `topic.callout` (reverse branch added); writer routes `callout` into `children.callout` (XMind Zen's real location) instead of a top-level field.
- **`style` dropped by reader/writer** — node bold (`style.properties.fo:font-weight`) is now read and written back losslessly. Verified on a real file: 11 bold topics survive xmind→JSON→xmind→read (11→11). The **JSON channel** is now the lossless round-trip; the md channel remains lossy by design (style/images/thumbnails have no md equivalent).

See `SKILL.md` "Design Rationale" for the positioning update: md→xmind is the headline feature (LLM-native generation), xmind→md is a human-facing diff/share/search copy, xmind→JSON is the LLM-consumption channel.

## v0.6 highlights

- **Default theme injection** — Zen writes inject a built-in colorful theme (`assets/default_theme.json`, extracted from a real XMind file: 6-color branch palette, NeverMind font, sized topics) so generated maps open polished instead of plain. Override: `--theme <file.json>` for custom, `--no-theme` for plain. Python API: `write_xmind(..., theme=dict|None|USE_DEFAULT_THEME)`.

## v0.5.1 Fixes

- **CSV Excel encoding** — CSV now written as UTF-8 with BOM (`utf-8-sig`); Windows Excel no longer shows garbled Chinese. (stdout output stays BOM-free.)
- **Markdown-import detached/summary note bug** — `[游离]`/`[概要]` topics' `note`/`labels`/`makers`/`link` were attaching to the parent node instead of the topic itself; fixed. Caught by a stress roundtrip with detached+note fixtures.

## v0.5 highlights

- **Legacy (XMind 8) write** — `write_xmind(..., format="legacy")` / `xmind-tool write --format legacy` emits `content.xml` + `META-INF/manifest.xml` (title tree + note/labels/makers/link roundtrip)
- **Session memory** — `read --session <id>` caches to `.xmind-cache/<session>/` next to source (cwd fallback); `memory <file> --session <id>` retrieves. Resume long-context edits by id without re-parsing

## v0.3 highlights

- **CSV export** — flat table with sheet/depth/path/title/note/labels/makers/link columns
- **OPML export** — OPML 2.0 outline preserving full hierarchy + `_note`/`_labels`/`_makers`/`_link` custom attributes

## v0.2 highlights

- **Markdown → .xmind import** (`convert notes.md -o out.xmind`)
- **Styles/icons roundtrip-safe** (`read_xmind_full` / `write_xmind_full` preserve `styles.json` and `manifest.json` byte-for-byte)
- **Globally installed CLI** (via `pip install -e .`)
