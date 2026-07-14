---
name: xmind
description: "Read, write, and convert .xmind mind map files losslessly (Zen + Legacy formats) to/from JSON, YAML, Markdown, CSV, and OPML — without needing XMind installed. Provides a Python API (xmind_tool) and a global CLI (xmind-tool). Use whenever the user mentions xmind, .xmind, mind map, mindmap, 思维导图, 脑图, 导图, or wants to convert between xmind and any text format (md/json/yaml/csv/opml), import markdown as a mind map, or batch-process .xmind files — even if they don't say 'xmind' explicitly."
metadata:
  version: "0.7.1"
---

# xmind — Lightweight .xmind Read/Write/Convert

A small, dependency-light toolkit for working with `.xmind` mind map files. Read them, write them, convert them to other formats, import markdown as a mind map, export to CSV/OPML — without needing XMind installed.

## What It Does

- **Read** any `.xmind` file to a normalized Python `dict` (handles both XMind 7 legacy `content.xml` and XMind 8+ `content.json` formats)
- **Preserves summary boxes, detached topics, callouts** — the Zen reader self-parses `content.json` instead of relying on xmindparser, which otherwise silently drops these structures (only `children.attached` is walked there)
- **Write** `.xmind` files in **either** format:
  - **Zen** (default): `content.json` + `metadata.json` + `manifest.json` — XMind 8+/Zen/2020+, roundtrip-safe with summary/detached/callout
  - **Legacy**: `content.xml` + `META-INF/manifest.xml` — XMind 8 compatible (title tree + note/labels/makers/link; summary/detached not preserved by the legacy roundtrip)
- **Convert** bidirectionally between `.xmind` and JSON / YAML / Markdown
- **Import** Markdown documents as `.xmind` (reverse direction)
- **Export to CSV** (flattened, one row per topic with breadcrumb path)
- **Export to OPML** (preserves hierarchy, with custom `_note`/`_labels`/`_makers`/`_link` attributes)
- **Preserve styles/icons/themes** — full roundtrip-safe `styles.json` and `manifest.json` pass-through (Zen)
- **Default theme injection** — Zen writes inject a built-in colorful theme (extracted from a real XMind file: 6-color palette, NeverMind font, sized central/main/sub topics) so generated maps look polished instead of plain black-on-white. Override with a custom theme JSON or disable with `--no-theme`
- **Session memory** — `read --session <id>` caches parsed output to `.xmind-cache/<session>/` next to the source file (falls back to `cwd/.xmind-cache/` if the source dir is read-only); `memory <file> --session <id>` retrieves it for breakpoint resume after long-context compression
- **Globally installed CLI** — `xmind-tool` works from any directory after `pip install -e .`

## Design Rationale (read this first)

This toolkit is **directionally asymmetric** by design. Understanding why prevents misuse:

- **md → xmind is the headline feature.** LLMs naturally emit indented lists / markdown; they do **not** natively emit Zen `content.json` with `id`/`theme`/`manifest`. Treating md as the human+LLM-readable intermediate, then converting to a visually-polished `.xmind`, is the LLM-native way to *generate* a mind map. This is the path to optimize for. **When generating a mind map from scratch (not converting existing md), read [`references/md-authoring-guide.md`](references/md-authoring-guide.md) first** — it gives the structural conventions (H1→sheet, H2→root, H3+→children), the node-attachment syntax (`>`/`**Labels:**`/`[概要]`/`[游离]`), what md cannot express (relationships/images/styles), and anti-patterns to avoid.

- **xmind → JSON/dict is the right channel for an LLM to *consume* an xmind.** `content.json` is already structured; reading it to a dict loses nothing the LLM needs. Do **not** convert to md just to feed an LLM — that adds a lossy step. As of v0.7.0 the reader is **lossless**: every feature real XMind files use (image, boundaries, relationships, extensions, style, id, layout state) is read into the dict and survives `xmind→xmind` round-trip.

- **xmind → md is a *human-facing* artifact, not an LLM-facing one.** Its value is a plain-text **copy** for diffing under git, sharing where `.xmind` can't render (GitHub/Slack/Obsidian), and grep/full-text search — not LLM consumption.

- **md round-trip (xmind→md→xmind) is lossy and not a goal.** XMind's visual style (`style.properties`, e.g. `fo:font-weight` bold) and image/attachment/thumbnail/relationship data have no md equivalent and are dropped on the md path. Inline markup (`**bold**`/`` `code` ``/`*ital*`) in headings is **stripped to plain text** on import — XMind expresses bold via `style.properties.fo:font-weight`, not text symbols. For a **lossless** round-trip use the **JSON channel** (`xmind_to_json` → `json_to_xmind`), which preserves style/summary/detached/callout/image/boundaries/relationships/extensions/id (verified zero-drop on 110 real files, see v0.7.0).

- **md scope = structure + text-expressible metadata only.** The md path covers the title tree plus `note`/`labels`/`makers`/`link`/`callout`/`summary`/`detached`/bullet lists. Visual style, images, thumbnails, and relationships belong to the JSON channel, not md.

## Why This Exists

- `xmind` on PyPI (v1.2.0) is a dead project — silently no-ops on the modern JSON-based XMind 8+ format
- `xmind-sdk-python` (official, GitHub) was archived in 2019 and never published to PyPI
- `xmindparser` (v1.2.2) reads both formats perfectly, but is **read-only**
- This tool bridges the gap: use `xmindparser` for read, handcrafted `zipfile + json` for write

## Quick Start

### As a Python module

```python
from xmind_tool import reader, writer, convert

# Read
sheets = reader.read_xmind("brain.xmind")           # list[sheet_dict]
print(sheets[0]["title"], "->", sheets[0]["topic"]["title"])

# Read with full metadata (styles, manifest)
full = reader.read_xmind_full("brain.xmind")        # {"sheets", "styles", "manifest"}

# Write (Zen, default)
new_sheets = [{
    "title": "My Map",
    "topic": {
        "title": "Root",
        "topics": [
            {"title": "Idea 1", "note": "some context", "labels": ["todo"]},
            {"title": "Idea 2", "topics": [{"title": "sub"}]},
        ],
    },
}]
writer.write_xmind(new_sheets, "out.xmind")                    # Zen (default)
writer.write_xmind(new_sheets, "out.xmind", format="legacy")   # XMind 8 compatible

# Convert
convert.xmind_to_markdown("brain.xmind", "brain.md")
convert.xmind_to_json("brain.xmind", "brain.json")
convert.xmind_to_csv("brain.xmind", "brain.csv")       # NEW in v0.3
convert.xmind_to_opml("brain.xmind", "brain.opml")     # NEW in v0.3

# Reverse
convert.json_to_xmind("structure.json", "out.xmind")
convert.markdown_to_xmind("notes.md", "out.xmind")
```

### As a globally-installed CLI command

```bash
# Read to stdout (default: JSON)
xmind-tool read brain.xmind
xmind-tool read brain.xmind --format yaml
xmind-tool read brain.xmind --format md
xmind-tool read brain.xmind --format csv        # NEW in v0.3
xmind-tool read brain.xmind --format opml      # NEW in v0.3

# Save to file
xmind-tool read brain.xmind --output brain.json

# Write from JSON/YAML/Markdown
xmind-tool write structure.json --output out.xmind                 # default theme
xmind-tool write notes.md --output out.xmind --no-theme            # plain (no theme)
xmind-tool write structure.json --output out.xmind --format legacy # XMind 8
xmind-tool write structure.json --output out.xmind --theme my.json # custom theme

# Auto-detect direction from extensions
xmind-tool convert brain.xmind --output brain.json
xmind-tool convert brain.xmind --output brain.md
xmind-tool convert brain.xmind --output brain.csv       # NEW in v0.3
xmind-tool convert brain.xmind --output brain.opml      # NEW in v0.3
xmind-tool convert notes.md --output out.xmind                      # default theme
xmind-tool convert notes.md --output out.xmind --format legacy      # NEW in v0.5
xmind-tool convert notes.md --output out.xmind --no-theme           # NEW in v0.6

# Session memory (breakpoint resume across long contexts)
xmind-tool read brain.xmind --format md --session my-sess   # parse + cache to .xmind-cache/my-sess/
xmind-tool memory brain.xmind --session my-sess              # retrieve cached markdown later

# Show file summary
xmind-tool info brain.xmind
```

## Dict Schema (User-Facing)

You work with this shape; the writer translates it to XMind's internal format.

```python
sheet = {
    "title": "Sheet name",                 # required
    "topic": {                              # required (root topic)
        "title": "Root",
        "note": "optional plain text note",
        "labels": ["tag1", "tag2"],
        "link": "https://...",              # URL or xmind:// internal ref
        "makers": ["priority-1"],           # marker/priority IDs
        "callout": ["标注框文字"],           # callout boxes (string list)
        "topics": [                         # attached children
            {"title": "Child A", ...},
            {"title": "Child B", ...},
        ],
        "summary": [                        # summary boxes (topic dicts)
            {"title": "概要框文字", "range": "(0,5)", ...},
        ],
        "detached": [                       # detached/floating topics
            {"title": "游离主题", ...},
        ],
    },
}
write_xmind([sheet, sheet2, ...], "out.xmind")  # list of sheets
```

## Output Format Reference

### Markdown (xmind → md)

- Sheet title → `# H1`
- Topic depth → `## H2`, `### H3`, etc.
- `note` → `>` blockquote
- `labels` → `**Labels:** a, b, c`
- `makers` → `**Makers:** ...`
- `link` → `[Link](url)`
- `callout` → `**Callout:** ...`
- `summary` (概要框) → 渲染在它括住的子节点**之后**（按 `range`），标题前缀 `[概要]`。不再是与兄弟并列的普通项 —— 这保留 XMind 概要框「大括号包住一组兄弟」的语义
- `detached` (游离主题) → 子层标题，前缀 `[游离]`
- `relationships` (关联线) → 各 sheet 末尾只读注脚段 `## 关联`，形如 ``- `端点A` ↔ `端点B`（标题）``。端点用反引号包标题，端点缺失时回退 id 前缀（不裸露 uuid）。**这是 derived 的展示信息，不是创作语法**：关系线本体在 JSON 通道无损往返，md→xmind 时该段整体丢弃

### Markdown (md → xmind)

- `[概要] xxx` 标题 → 还原为父节点的 `summary`
- `[游离] xxx` 标题 → 还原为父节点的 `detached`
- `## 关联` 段 → **整段丢弃**（只读注脚，关系线不在 md 通道创作；要建关联线请用 JSON 通道的 `relationships`）
- 其余按 H1/H2/H3+ 层级 + `>`/`**Labels:**`/`**Makers:**`/`[text](url)` 解析

### CSV (xmind → csv, NEW in v0.3)

Flat table — one row per topic. Columns:

| Column | Meaning |
|---|---|
| `sheet` | sheet title |
| `depth` | nesting depth (0 = root) |
| `path` | breadcrumb like `Root > Branch > Leaf` |
| `title` | topic title |
| `note` | topic note (empty if none) |
| `labels` | comma-separated labels (empty if none) |
| `makers` | comma-separated makers (empty if none) |
| `link` | topic link (empty if none) |

Multiple sheets share one CSV file; rows are differentiated by the `sheet` column.

### OPML (xmind → opml, NEW in v0.3)

OPML 2.0 outline that preserves full hierarchy. Each xmind sheet becomes a top-level `<outline>` (with the sheet title as `text`); the root topic is its first child. Custom xmind metadata goes into underscore-prefixed attributes:

- `_note` — topic's note
- `_labels` — comma-separated labels
- `_makers` — comma-separated makers
- `_link` — topic's link

Sample output:

```xml
<opml version="2.0">
  <head><title>brain.xmind</title></head>
  <body>
    <outline text="Sheet Title">
      <outline text="Root Topic" _note="remember this">
        <outline text="Branch 1" _labels="important">
          <outline text="Leaf" _link="https://example.com"/>
        </outline>
      </outline>
    </outline>
  </body>
</opml>
```

OPML is read-compatible with many outliners (OmniOutliner, WorkFlowy importers, etc.).

### JSON / YAML

A faithful dump of the dict tree. YAML is `allow_unicode=True` so Chinese works.

## Markdown Import Syntax

When importing a Markdown file, this skill recognizes:

| Markdown | Becomes |
|---|---|
| `# H1` | new sheet title (first H1 required) |
| `## H2` | root topic of the current sheet |
| Second `## H2` under same H1 | new sheet (H2 as both title and root) |
| `### H3`, `#### H4`, ... | nested child topics (depth = heading level - 2) |
| `- item` / `* item` / `+ item` | attached child topic of the current topic; indentation (4 spaces per level) nests deeper [v0.6.1] |
| `> quoted text` | current topic's note (multi-line `>` accumulates) |
| `**Labels:** A, B, C` | current topic's labels |
| `**Makers:** task, flag` | current topic's markers |
| `**Callout:** text` | current topic's callout box [v0.6.1] |
| `[text](url)` | current topic's link |
| `**bold**` / `` `code` `` / `*italic*` **inside headings** | stripped to plain text (XMind expresses bold via `style.properties.fo:font-weight`, not text symbols) [v0.6.1] |
| `[概要] title` heading | parent topic's summary box (range inferred from preceding attached children) |
| `[游离] title` heading | parent topic's detached topic |
| `## 关联` section | **dropped entirely** (read-only footnote; relationships belong to the JSON channel) [v0.7.1] |
| ` ``` ` fenced code blocks | content is ignored (no parsing inside) |

**Reverse direction (xmind → md)** mirrors this: note→`>`, labels/makers/callout→`**Key:** value`, link→`[Link](url)`, summary→`[概要]` heading rendered after its bracketed children, detached→`[游离]` heading, relationships→`## 关联` footnote section at end of each sheet (endpoints rendered as `` `title` ↔ `title` ``) [v0.7.1]. `style` (bold/color) is **not** rendered to md — it lives in the JSON channel.

## Trigger Conditions

**English:** xmind, .xmind, mind map, mindmap, mental model, brainstorm, read xmind, write xmind, convert xmind, xmind to json, xmind to markdown, xmind to yaml, xmind to csv, xmind to opml, json to xmind, yaml to xmind, markdown to xmind, md to xmind, import markdown as mindmap, export mindmap to csv, export mindmap to opml, install xmind-tool

**中文:** xmind, 思维导图, 脑图, 导图, 心智图, 读 xmind, 写 xmind, 转换脑图, 脑图转 markdown, 脑图转 json, 脑图转 csv, 脑图转 opml, 从 json 生成 xmind, 从 yaml 生成 xmind, 从 markdown 生成 xmind, 导入 md 为脑图, 批量转换, 导出 csv, 导出 opml

## Version History & Reference

Full changelog (v0.2 → v0.7.1), installation steps, and project layout live in [`references/CHANGELOG.md`](references/CHANGELOG.md) — kept out of this trigger file to keep context lean.

**Latest (v0.7.1):** CLI console-script (`xmind-tool`) now actually dispatches subcommands — previously `main(argv=None)` printed help and exited 0 because it never read `sys.argv` (the bug was invisible to tests, which pass `argv` explicitly). md export now renders `relationships` as a read-only `## 关联` footnote section at the end of each sheet (endpoints as `` `title` ↔ `title` ``); md→xmind drops that section by design (relationships belong to the JSON channel). Added 2 regression tests for the CLI dispatch path.

**v0.7.0:** real-world robustness audit on 110 XMind Zen files → reader/writer now lossless for `image`/`boundaries`/`relationships`/`extensions`/`style`/`id`/layout keys (zero feature-drop verified on all 110 files; 616 images, 55 relationships, 18 boundaries preserved 1:1 through read→write→read). md round-trip stays lossy by design.

## Limitations (v0.7.1)

- **md round-trip is lossy by design** — `style` (bold/color/size), images, thumbnails, and relationships have no md equivalent. Relationships are shown read-only in md (`## 关联` footnote) but not authored there; to create relationships use the **JSON channel** (`relationships` on the sheet dict). For lossless round-trip use the **JSON channel** (`xmind_to_json` → `json_to_xmind`), which preserves style/summary/detached/callout/image/boundaries/relationships/extensions/id (verified zero-drop on 110 real files in v0.7.0).
- **Legacy roundtrip is lossy for summary/detached/callout** — writing `format="legacy"` serializes the title tree + note/labels/makers/link, but XMind 8's `content.xml` summary/detached/callout elements aren't emitted (and xmindparser's legacy reader doesn't read them either, so roundtrip can't preserve them). Use Zen if you need those structures.
- **Style is preserved, not authored** — reader/writer round-trip existing `style` dicts losslessly (Zen), but you can't yet author new visual styles from a plain dict beyond passing a full `style` object (would need XMind's full styles.json schema).
- **Image *metadata* is preserved; image *bytes* are referenced, not copied** — the reader/writer preserve `image.src` (`xap:resources/<hash>.png`) and dimensions on the Zen round-trip, but the underlying PNG bytes inside the zip's `resources/` folder are not extracted/re-embedded by `write_xmind` (only `content.json` is rewritten). If you need byte-level image fidelity (copying the PNG into the new zip), use `read_xmind_full` + a custom writer that also copies `resources/*`. This is consistent with the "metadata is the LLM channel, bytes are the XMind app's job" split.
- **Relationships are pass-through, not editable** — `relationships` survive round-trip with valid `end1Id`/`end2Id`, but there's no high-level API to *author* new relationships by title (you'd need to pass raw `{end1Id, end2Id, title}` dicts and know the topic ids).
- **CSV/OPML are one-way** — there's no `csv_to_xmind` / `opml_to_xmind` (CSV is lossy; OPML reverse is feasible but out of scope).
- **Git Bash + console-script shim** — `xmind-tool.exe` may have arg-passing issues in Git Bash; use `python -m xmind_tool.cli` instead.
