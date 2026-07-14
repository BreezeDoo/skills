"""
xmind_tool.convert: .xmind 与其他格式互转。

支持：
- .xmind -> .json / .yaml / .md / .csv / .opml
- .json -> .xmind
- .yaml -> .xmind
- .md -> .xmind
"""
import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union

import yaml

from .reader import read_xmind
from .writer import write_xmind

PathLike = Union[str, Path]

# .xmind 输出的 fmt 别名
_TO_ALIASES = {
    "json": ".json",
    "yaml": ".yaml",
    "yml": ".yaml",
    "md": ".md",
    "markdown": ".md",
    "csv": ".csv",
    "opml": ".opml",
}


# ---------- .xmind -> 其他 ----------

def xmind_to_json(xmind_path: PathLike, out_path: PathLike) -> str:
    """把 .xmind 转为 .json，返回输出路径。"""
    data = read_xmind(xmind_path)
    out = Path(out_path)
    out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(out.resolve())


def xmind_to_yaml(xmind_path: PathLike, out_path: PathLike) -> str:
    """把 .xmind 转为 .yaml，返回输出路径。"""
    data = read_xmind(xmind_path)
    out = Path(out_path)
    out.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return str(out.resolve())


def _parse_range(rng: str) -> tuple[int, int] | None:
    """解析 XMind summary 的 range 字段（如 "(0,5)"），返回 [start, end) 半开区间。

    XMind range 表示概要框括住第 start..end-1 个 attached 子节点。
    无法解析时返回 None。
    """
    if not rng:
        return None
    import re
    m = re.match(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", str(rng))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _render_topic_md(topic: dict, level: int) -> list[str]:
    """递归渲染 topic 为 markdown 行。

    渲染顺序：标题 → note → labels → makers → link → callout →
    普通子节点(topics) → 游离主题(detached)。
    概要框(summary)按 range 插在被它括住的子节点之后，作为「括号收尾」行，
    而非与子节点并列 —— 这保留了 XMind 概要框「大括号包住一组兄弟」的语义。
    """
    lines = []
    heading = "#" * level
    title = topic.get("title", "")
    lines.append(f"{heading} {title}")

    note = topic.get("note")
    if note:
        lines.append("")
        for ln in note.split("\n"):
            lines.append(f"> {ln}")

    labels = topic.get("labels") or []
    if labels:
        lines.append("")
        lines.append(f"**Labels:** {', '.join(labels)}")

    makers = topic.get("makers") or []
    if makers:
        lines.append("")
        lines.append(f"**Makers:** {', '.join(makers)}")

    link = topic.get("link")
    if link and not link.startswith("["):
        lines.append("")
        lines.append(f"[Link]({link})")

    callouts = topic.get("callout") or []
    if callouts:
        lines.append("")
        lines.append(f"**Callout:** {', '.join(callouts)}")

    children = topic.get("topics") or []
    summaries = topic.get("summary") or []

    if children:
        # 把概要框按 range 归位：渲染到它括住的最后一个子节点之后。
        # range 缺失时默认括住全部子节点（挂在末尾）。
        pending_summaries = list(summaries)
        for i, child in enumerate(children):
            lines.append("")
            lines.extend(_render_topic_md(child, level + 1))
            # 检查是否有概要框在此处收尾（range 的 end == i+1）
            for s in list(pending_summaries):
                rng = _parse_range(s.get("range"))
                end = rng[1] if rng else len(children)
                if end == i + 1:
                    lines.append("")
                    lines.append(
                        f"{'#' * (level + 1)} [概要] {s.get('title', '')}"
                    )
                    pending_summaries.remove(s)
        # range 缺失或 end 超出 children 数的概要框，挂在末尾
        for s in pending_summaries:
            lines.append("")
            lines.append(f"{'#' * (level + 1)} [概要] {s.get('title', '')}")

    # 游离主题（detached）：浮动主题，作为子层并附「游离」标记
    for d in topic.get("detached") or []:
        d = dict(d)
        d["title"] = f"[游离] {d.get('title', '')}"
        lines.append("")
        lines.extend(_render_topic_md(d, level + 1))

    return lines


def _collect_topic_titles(topic: dict, out: dict) -> None:
    """递归收集 topic 树里所有 id → title 的映射（用于解析关系线端点）。"""
    tid = topic.get("id")
    if tid and tid not in out:
        out[tid] = topic.get("title", "")
    for c in (topic.get("topics") or []):
        _collect_topic_titles(c, out)
    for d in (topic.get("detached") or []):
        _collect_topic_titles(d, out)
    for s in (topic.get("summary") or []):
        _collect_topic_titles(s, out)


def _render_relationships(sheet: dict, id_titles: dict) -> list[str]:
    """把 sheet 级 relationships 渲染为 md 末尾的只读注脚段。

    形如：
        ## 关联
        - `f-22-task_a-type.txt` ↔ `mf_bhv_profile_include.txt`（依赖）

    设计：这是「读出来的注脚」，不是创作语法。关系线本体在 JSON 通道无损
    往返；这里只是让看 md 的人能感知「哪些节点之间有关系」。端点用反引号
    包住标题，title 缺失时回退到端点 id 前缀，避免裸 uuid 污染正文。
    """
    rels = sheet.get("relationships") or []
    if not rels:
        return []
    lines = ["", "## 关联"]
    for r in rels:
        e1 = r.get("end1Id")
        e2 = r.get("end2Id")
        t1 = id_titles.get(e1, (e1[:8] + "…" if e1 else "?"))
        t2 = id_titles.get(e2, (e2[:8] + "…" if e2 else "?"))
        title = r.get("title") or ""
        suffix = f"（{title}）" if title else ""
        lines.append(f"- `{t1}` ↔ `{t2}`{suffix}")
    return lines


def xmind_to_markdown(xmind_path: PathLike, out_path: PathLike) -> str:
    """把 .xmind 转为 .md，每个 sheet 一个 H1。

    relationships 渲染为各 sheet 末尾的只读注脚段（`## 关联`），端点标题
    解析自 topic.id。关系线本身在 JSON 通道无损往返，此处仅为可读性。
    """
    data = read_xmind(xmind_path)
    out = Path(out_path)

    md_lines = []
    for sheet in data:
        md_lines.append(f"# {sheet.get('title', 'Untitled')}")
        md_lines.append("")
        topic = sheet.get("topic", {})
        id_titles: dict = {}
        if topic:
            _collect_topic_titles(topic, id_titles)
            md_lines.extend(_render_topic_md(topic, level=2))
        # sheet 级关系线 → 末尾注脚（放在 sheet 内容之后、下个 sheet 之前）
        md_lines.extend(_render_relationships(sheet, id_titles))
        md_lines.append("")  # sheet 间空行

    out.write_text("\n".join(md_lines), encoding="utf-8")
    return str(out.resolve())


def xmind_to(xmind_path: PathLike, out_path: PathLike, fmt: str) -> str:
    """通用入口：.xmind -> fmt 指定格式。"""
    fmt_norm = fmt.lower()
    if fmt_norm not in _TO_ALIASES:
        raise ValueError(
            f"不支持的输出格式: {fmt!r}。可选: {sorted(set(_TO_ALIASES.values()))}"
        )
    if fmt_norm == "json":
        return xmind_to_json(xmind_path, out_path)
    if fmt_norm in ("yaml", "yml"):
        return xmind_to_yaml(xmind_path, out_path)
    if fmt_norm in ("md", "markdown"):
        return xmind_to_markdown(xmind_path, out_path)
    if fmt_norm == "csv":
        return xmind_to_csv(xmind_path, out_path)
    if fmt_norm == "opml":
        return xmind_to_opml(xmind_path, out_path)
    raise ValueError(f"Unhandled format: {fmt!r}")  # 不会触发，仅防御


# ---------- 其他 -> .xmind ----------

def json_to_xmind(json_path: PathLike, out_path: PathLike, fmt: str = "zen", theme=...) -> str:
    """读 .json（list[sheet]）并写为 .xmind。"""
    from .writer import USE_DEFAULT_THEME
    if theme is ...:
        theme = USE_DEFAULT_THEME
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("JSON 顶层必须是 list[sheet]")
    return write_xmind(data, out_path, format=fmt, theme=theme)


def yaml_to_xmind(yaml_path: PathLike, out_path: PathLike, fmt: str = "zen", theme=...) -> str:
    """读 .yaml（list[sheet]）并写为 .xmind。"""
    from .writer import USE_DEFAULT_THEME
    if theme is ...:
        theme = USE_DEFAULT_THEME
    data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("YAML 顶层必须是 list[sheet]")
    return write_xmind(data, out_path, format=fmt, theme=theme)


# ---------- .xmind -> .csv ----------

_CSV_HEADER = ["sheet", "depth", "path", "title", "note", "labels", "makers", "link"]


def _walk_topic(topic: dict, depth: int, path: list[str], out: list[list[str]],
                sheet_title: str) -> None:
    """DFS topic 树，每节点输出一行。path 累积为面包屑。

    attached 子节点用普通 path；概要框(summary)/游离主题(detached)在 path
    前加标记，便于在扁平表里区分结构性质。
    """
    title = topic.get("title", "")
    new_path = path + [title]
    out.append([
        sheet_title,
        str(depth),
        " > ".join(new_path),
        title,
        topic.get("note", "") or "",
        ", ".join(topic.get("labels") or []),
        ", ".join(topic.get("makers") or []),
        topic.get("link", "") or "",
    ])
    for child in (topic.get("topics") or []):
        _walk_topic(child, depth + 1, new_path, out, sheet_title)
    # 概要框：path 插入「[概要]」标记
    for s in (topic.get("summary") or []):
        _walk_topic(s, depth + 1, path + [f"[概要]{title}"], out, sheet_title)
    # 游离主题：path 插入「[游离]」标记
    for d in (topic.get("detached") or []):
        _walk_topic(d, depth + 1, path + [f"[游离]{title}"], out, sheet_title)


def xmind_to_csv(xmind_path: PathLike, out_path: PathLike) -> str:
    """把 .xmind 拍平为 CSV（一行一 topic，列：sheet/depth/path/title/note/labels/makers/link）。"""
    data = read_xmind(xmind_path)
    rows: list[list[str]] = []
    for sheet in data:
        topic = sheet.get("topic", {})
        if topic:
            _walk_topic(topic, 0, [], rows, sheet.get("title", ""))

    out = Path(out_path)
    # utf-8-sig：写入 UTF-8 BOM，让 Windows Excel 自动识别为 UTF-8，
    # 否则无 BOM 的 UTF-8 CSV 在 Excel 里被按 GBK 解码，中文乱码。
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_CSV_HEADER)
        writer.writerows(rows)
    return str(out.resolve())


# ---------- .xmind -> .opml ----------

def _topic_to_outline(topic: dict) -> ET.Element:
    """topic dict -> OPML <outline> element。"""
    elem = ET.Element("outline", {"text": topic.get("title", "")})
    if topic.get("note"):
        elem.set("_note", topic["note"])
    if topic.get("labels"):
        elem.set("_labels", ", ".join(topic["labels"]))
    if topic.get("makers"):
        elem.set("_makers", ", ".join(topic["makers"]))
    if topic.get("link"):
        elem.set("_link", topic["link"])
    if topic.get("callout"):
        elem.set("_callout", ", ".join(topic["callout"]))
    # 概要框：作为带 _type=summary 标记的子 outline
    for s in (topic.get("summary") or []):
        child = _topic_to_outline(s)
        child.set("_type", "summary")
        elem.append(child)
    # 游离主题：作为带 _type=detached 标记的子 outline
    for d in (topic.get("detached") or []):
        child = _topic_to_outline(d)
        child.set("_type", "detached")
        elem.append(child)
    for child in (topic.get("topics") or []):
        elem.append(_topic_to_outline(child))
    return elem


def xmind_to_opml(xmind_path: PathLike, out_path: PathLike) -> str:
    """把 .xmind 转为 OPML 2.0：每个 sheet 是一个顶层 <outline>。"""
    data = read_xmind(xmind_path)

    opml = ET.Element("opml", {"version": "2.0"})
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = Path(str(xmind_path)).name
    body = ET.SubElement(opml, "body")

    for sheet in data:
        # 用 sheet.title 作为外层 outline，root topic 作为内层
        sheet_outline = ET.SubElement(body, "outline", {"text": sheet.get("title", "Untitled")})
        root = sheet.get("topic", {})
        if root:
            sheet_outline.append(_topic_to_outline(root))

    out = Path(out_path)
    # pretty print 用 ET.indent（py3.9+）
    if hasattr(ET, "indent"):
        ET.indent(opml, space="  ")
    tree = ET.ElementTree(opml)
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return str(out.resolve())


# ---------- .md -> .xmind ----------

_H1_RE = re.compile(r"^#\s+(.+?)\s*$")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_HN_RE = re.compile(r"^(#{3,})\s+(.+?)\s*$")
_BQ_RE = re.compile(r"^>\s?(.*)$")
_LABELS_RE = re.compile(r"^\*\*Labels:\*\*\s*(.+?)\s*$")
_MAKERS_RE = re.compile(r"^\*\*Makers:\*\*\s*(.+?)\s*$")
_CALLOUT_RE = re.compile(r"^\*\*Callout:\*\*\s*(.+?)\s*$")
_LINK_RE = re.compile(r"^\[.+?\]\((.+?)\)\s*$")

# 标题内联标记剥离：XMind 的加粗语义在 style.properties.fo:font-weight，不在
# title 文本里。md 的 **bold** / `code` / *italic* 是文本内符号，若原样保留，
# XMind 会显示出带星号/反引号的字面文本。这里把内联标记剥离成纯文本。
# 注意顺序：先去行内代码（避免代码内的星号被误当强调），再去加粗，再去斜体。
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC_RE = re.compile(r"\*(.+?)\*|_(.+?)_")

# 无序列表项：可选缩进 + (- / * / +) + 空格 + 标题。
# 缩进用 capture，之后 expandtabs 算嵌套深度。
_LIST_RE = re.compile(r"^(?P<indent>[ \t]*)[-*+]\s+(?P<title>.+?)\s*$")


def _strip_inline_markup(text: str) -> str:
    """剥离标题里的内联标记，返回纯文本。

    顺序很重要：先 `code`（保护代码内的星号），再 **bold**/__bold__，
    再 *italic*/_italic_。只剥一层配对的标记，不递归。
    """
    text = _INLINE_CODE_RE.sub(lambda m: m.group(1), text)
    text = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    return text


def _flush_note(stack: list[dict], note_buf: list[str]) -> None:
    """把累积的 note 行附加到栈顶 topic，清空 buffer。"""
    if not note_buf:
        return
    text = "\n".join(note_buf).strip()
    if text and stack:
        # 合并：若已有 note，用换行连接
        if "note" in stack[-1]:
            stack[-1]["note"] = stack[-1]["note"] + "\n" + text
        else:
            stack[-1]["note"] = text
    note_buf.clear()


def _parse_markdown(text: str) -> list[dict]:
    """解析 markdown 文本，返回 list[sheet_dict]。

    规则：
    - H1 → 新 sheet，title = H1 文本
    - H2 → 当前 sheet 的 root；若当前 sheet 已有 root，则开新 sheet（title = H2 文本）
    - H3+ → 嵌套子 topic（深度 = heading 级别 - 2）
    - 缺 H1 且只有 ## H2 → 用 "Imported" 作为 sheet title
    """
    sheets: list[dict] = []
    cur_sheet: dict | None = None
    has_root: bool = False          # 当前 sheet 是否已设 root
    stack: list[dict] = []          # topic 嵌套栈
    note_buf: list[str] = []
    in_code = False
    # 关联注脚段跳过：xmind→md 会渲染 `## 关联` 段，里面是只读的 `- A ↔ B`。
    # 该段是 derived 的展示信息，不是用户输入的 topic 树；md→xmind 时直接丢弃。
    # 跳过范围：从 `## 关联` 起，直到遇到下一个 `# H1` 或非 `## 关联` 的 `## H2`。
    skip_rel = False

    def new_sheet(title: str, root_title: str) -> dict:
        s = {"title": title, "topic": {"title": root_title}}
        sheets.append(s)
        return s

    for line in text.splitlines():
        # 切换代码块
        if line.strip().startswith("```"):
            if not in_code:
                _flush_note(stack, note_buf)
            in_code = not in_code
            continue
        if in_code:
            continue

        # 块引用 → note
        m = _BQ_RE.match(line)
        if m:
            note_buf.append(m.group(1))
            continue
        else:
            _flush_note(stack, note_buf)

        # 关联注脚段处理：`## 关联` 是只读 derived 段，整段丢弃。
        # 用 H1/H2 的匹配来判断段结束，避免重复正则。
        m_h1 = _H1_RE.match(line)
        m_h2 = _H2_RE.match(line)
        if skip_rel:
            # 遇到任何 H1，或非 `## 关联` 的 H2，就结束跳过
            if m_h1 or (m_h2 and _strip_inline_markup(m_h2.group(1).strip()) != "关联"):
                skip_rel = False
                # 落入下方 H1/H2 正常处理，不 continue
            else:
                # 仍在注脚段内（含 `## 关联` 自身及其 `- A ↔ B` 行），跳过
                continue

        # H1 → 新 sheet
        if m_h1:
            title = _strip_inline_markup(m_h1.group(1).strip())
            cur_sheet = new_sheet(title, "Root")
            has_root = False
            stack = [cur_sheet["topic"]]
            continue

        # H2 → 当前 sheet 的 root；若已设 root，则开新 sheet（除非是 `## 关联` 注脚段）
        if m_h2:
            title = _strip_inline_markup(m_h2.group(1).strip())
            if title == "关联":
                # 进入只读关联注脚段：丢弃直到下一个 H1/非关联 H2
                skip_rel = True
                continue
            if cur_sheet is None:
                # 缺 H1 的情况：第一个 H2 用 "Imported" 作 sheet title
                cur_sheet = new_sheet("Imported", title)
                has_root = True
            elif has_root:
                # 已有 root 的 sheet 内出现第二个 H2 → 开新 sheet（H2 自作 title + root）
                cur_sheet = new_sheet(title, title)
                has_root = True
            else:
                # 当前 sheet 还没 root → 用 H2 设置 root
                cur_sheet["topic"] = {"title": title}
                has_root = True
            stack = [cur_sheet["topic"]]
            continue

        # H3+ → 嵌套子 topic
        m = _HN_RE.match(line)
        if m:
            level = len(m.group(1))   # 3 for ###, 4 for ####, ...
            title = _strip_inline_markup(m.group(2).strip())
            # root 是 H2，H3 是 root 的 child (stack 深度 1)
            target_depth = level - 2   # H3 -> 1, H4 -> 2

            # 概要框 / 游离主题 标记：[概要] xxx / [游离] xxx
            # 它们不是普通子节点，而是挂在「本该作为父」的节点上：
            #   [概要] → parent.summary；[游离] → parent.detached
            # parent 即 stack 在 target_depth-1 处的节点。
            #
            # range 从位置推断：概要框括住它之前已出现的全部 attached 子节点。
            # 形如「A / B / C / [概要] / D」→ range (0,3) 括住 A,B,C，D 在括号外。
            # 这与 XMind「[概要] 渲染在被括子节点之后」的约定一致，且避免
            # range 覆盖全部子节点（XMind 对满覆盖 range 不渲染括号）。
            if title.startswith("[概要] "):
                sum_title = title[len("[概要] "):]
                # 调整 stack 到父层
                while len(stack) > target_depth:
                    stack.pop()
                parent = stack[-1] if stack else None
                if parent is not None:
                    n_before = len(parent.get("topics", []))
                    node = {
                        "title": sum_title,
                        "range": f"(0,{n_before})",
                    }
                    parent.setdefault("summary", []).append(node)
                    # 压栈：让紧随的 note/labels/makers/link 归属到概要框自己，
                    # 而非父节点。下一个标题的 pop 会把它弹出。
                    stack.append(node)
                continue
            if title.startswith("[游离] "):
                dt_title = title[len("[游离] "):]
                while len(stack) > target_depth:
                    stack.pop()
                parent = stack[-1] if stack else None
                if parent is not None:
                    node = {"title": dt_title}
                    parent.setdefault("detached", []).append(node)
                    # 同概要框：压栈让后续 note 等元数据归属游离主题自己。
                    stack.append(node)
                continue

            while len(stack) > target_depth:
                stack.pop()
            parent = stack[-1] if stack else None
            new_topic = {"title": title}
            if parent is not None:
                parent.setdefault("topics", []).append(new_topic)
            elif cur_sheet is not None:
                cur_sheet["topic"] = new_topic
            stack.append(new_topic)
            continue

        # 无序列表项：`- item` / `* item` / `+ item`，可带缩进表示嵌套。
        # 列表项当作「当前栈顶的 attached 子节点」，嵌套深度由缩进决定：
        #   0 缩进 → root 的子节点（同 H3 的深度 1）；每 4 空格加深一层。
        # 这样列表与标题树自然融合，列表项也可挂 note/labels 等元数据。
        m = _LIST_RE.match(line)
        if m:
            indent = len(m.group("indent").expandtabs(4))
            raw_title = m.group("title").strip()
            if not raw_title:
                continue
            title = _strip_inline_markup(raw_title)
            target_depth = indent // 4 + 1
            # 切到目标父层（target_depth-1），与 H3+ 的栈操作一致
            while len(stack) > target_depth:
                stack.pop()
            # 确保 target_depth-1 不越过 root：列表项不能比 root 还浅
            if len(stack) < target_depth:
                stack = [cur_sheet["topic"]] if cur_sheet else []
            parent = stack[-1] if stack else None
            if parent is not None:
                node = {"title": title}
                parent.setdefault("topics", []).append(node)
                stack.append(node)
            continue

        # **Labels:** ...
        m = _LABELS_RE.match(line)
        if m:
            if stack:
                stack[-1]["labels"] = [s.strip() for s in m.group(1).split(",") if s.strip()]
            continue

        # **Makers:** ...
        m = _MAKERS_RE.match(line)
        if m:
            if stack:
                stack[-1]["makers"] = [s.strip() for s in m.group(1).split(",") if s.strip()]
            continue

        # **Callout:** ... → 标注框（与 reader 的 callout 字段对应，往返闭合）
        m = _CALLOUT_RE.match(line)
        if m:
            if stack:
                stack[-1].setdefault("callout", []).append(m.group(1).strip())
            continue

        # [text](url)
        m = _LINK_RE.match(line)
        if m:
            if stack:
                stack[-1]["link"] = m.group(1)
            continue

    # 文件结束 flush 一次
    _flush_note(stack, note_buf)

    return sheets


def markdown_to_xmind(md_path: PathLike, out_path: PathLike, fmt: str = "zen", theme=...) -> str:
    """读 .md 并写为 .xmind。"""
    from .writer import USE_DEFAULT_THEME
    if theme is ...:
        theme = USE_DEFAULT_THEME
    text = Path(md_path).read_text(encoding="utf-8")
    sheets = _parse_markdown(text)
    if not sheets:
        raise ValueError("Markdown 解析后无有效 sheet（至少需要一个 # H1 或 ## H2）")
    return write_xmind(sheets, out_path, format=fmt, theme=theme)
