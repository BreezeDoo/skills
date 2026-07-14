"""
xmind_tool.writer: 将 dict 写入 .xmind 文件。

支持两种输出格式：
- Zen (默认): zip + content.json + metadata.json + manifest.json — XMind 8+/Zen/2020+
- Legacy: zip + content.xml + META-INF/manifest.xml — XMind 8 兼容

接受用户友好的 dict 结构（topics 直接挂在 topic 下），内部翻译为各格式规范的
内部结构。
"""
import io
import json
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

# 在 XMind 文件里用到的子节点容器的内部 key
_CHILDREN_KEY = "children"
_ATTACHED_KEY = "attached"

# topic 字段直接透传的白名单（note/link/makers 等）。
# summary / detached / callout 不在此列：它们需递归为 children.summary /
# children.detached / children.callout（XMind Zen 把这三类都放在 children 容器里）。
# style 原样透传：XMind 的节点级视觉样式（如 fo:font-weight 加粗）藏在
# topic.style.properties，不在 title 文本里，故直接保留整个 style dict。
# image/boundaries/extensions/customWidth/width/position/titleUnedited 同理：
# 真实文件普遍存在、语义=原样存在，透传让 xmind→xmind 往返保真（md 不渲染）。
_TOPIC_PASS_FIELDS = {
    "note",
    "labels",
    "link",
    "makers",
    "image",
    "style",
    "boundaries",
    "extensions",
    "customWidth",
    "width",
    "position",
    "titleUnedited",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _to_xmind_topic(topic: dict, structure: str = "") -> dict:
    """把用户 dict 翻译为 XMind 内部 topic 结构。

    structure 仅对根 topic 生效（XMind 把 structureClass 放在 rootTopic 上）。
    """
    if "title" not in topic:
        raise ValueError("每个 topic 必须有 'title' 字段")

    children = topic.get("topics", [])
    summaries = topic.get("summary", [])
    detached = topic.get("detached", [])
    callouts = topic.get("callout", [])
    # id 保留：若 reader 读出了原 id（往返场景），原样写回；
    # 否则新生成。这关系到 relationships 的 end1Id/end2Id 是否仍指向有效 topic。
    out = {
        "id": topic.get("id") or _new_id("t"),
        "class": "topic",
        "title": topic["title"],
    }
    # 根 topic 的布局类（XMind 需要它来决定渲染算法）
    if structure:
        out["structureClass"] = structure

    # 透传白名单字段
    for f in _TOPIC_PASS_FIELDS:
        if f in topic and topic[f] is not None:
            out[_field_to_xmind(f)] = _value_to_xmind(f, topic[f])

    # 汇总非空子结构：attached / summary / detached 都进 children 容器
    # 概要框的 range 不挂在 topic 上，而是记到 summaries_meta，稍后写到
    # topic 顶层 summaries[]（children 的兄弟键）—— 这是 XMind Zen 真实格式。
    child_groups: dict = {}
    summaries_meta: list[dict] = []
    if children:
        child_groups[_ATTACHED_KEY] = [_to_xmind_topic(c) for c in children]
    if summaries:
        # children.summary 放概要文本 topic；range 写到 summaries[] 用 topicId 关联
        sum_out = []
        n_attached = len(children)
        for s in summaries:
            so = _to_xmind_topic(s)
            # range 缺失时默认括住全部 attached 子节点（XMind 语义）
            rng = s.get("range") or f"({0},{n_attached})"
            summaries_meta.append({
                "id": _new_id("sm"),
                "range": rng,
                "topicId": so["id"],
            })
            sum_out.append(so)
        child_groups["summary"] = sum_out
    if detached:
        child_groups["detached"] = [_to_xmind_topic(d) for d in detached]
    if callouts:
        # callout 在 dict 里是字符串列表（reader 读出的形态）；
        # XMind Zen 把标注框存为 children.callout 的 topic 列表，每个 {id,title,...}。
        child_groups["callout"] = [
            _to_xmind_topic({"title": c} if isinstance(c, str) else c)
            for c in callouts
        ]
    if child_groups:
        out[_CHILDREN_KEY] = child_groups
    # 概要框 range 引用表：必须作为 children 的兄弟键存在，否则 XMind 无法
    # 确定概要框括住哪些子节点，会把概要框渲染成游离主题而非括号。
    if summaries_meta:
        out["summaries"] = summaries_meta

    return out


def _field_to_xmind(field: str):
    """user-dict 字段名 -> XMind 内部字段名。"""
    return {
        "note": "notes",
        "link": "href",
        "makers": "markers",
    }.get(field, field)


def _value_to_xmind(field: str, value):
    """特殊字段的 value 翻译。"""
    if field == "note":
        return {"plain": {"content": value}}
    if field == "makers":
        # user 给 ["priority-1"] -> [{"markerId": "priority-1"}]
        return [{"markerId": m} for m in value]
    return value


# XMind Zen 默认布局（顺时针思维导图）
_DEFAULT_STRUCTURE = "org.xmind.ui.map.clockwise"

# sheet 级原样透传的键（与 reader 的 _SHEET_PASSTHROUGH_KEYS 对应）。
# relationships（跨树连线，含 end1Id/end2Id）/legend（图例布局状态）等
# 真实文件普遍存在，往返时原样写回以保无损。
_SHEET_PASS_FIELDS = (
    "relationships", "legend", "topicPositioning", "class", "style",
)


def _to_xmind_sheet(sheet: dict) -> dict:
    """sheet dict -> XMind 内部 sheet 结构。"""
    if "title" not in sheet:
        raise ValueError("每个 sheet 必须有 'title' 字段")
    if "topic" not in sheet:
        raise ValueError("每个 sheet 必须有 'topic' 字段（根节点）")

    # structure 来自 reader 读到的 sheet["structure"]，缺失则用默认布局
    structure = sheet.get("structure") or _DEFAULT_STRUCTURE
    out = {
        # id 保留：reader 读出原 id 则原样写回，否则新生成
        "id": sheet.get("id") or _new_id("s"),
        "class": "sheet",
        "title": sheet["title"],
        "rootTopic": _to_xmind_topic(sheet["topic"], structure=structure),
    }
    # 透传 sheet 级非结构化键
    for f in _SHEET_PASS_FIELDS:
        if f in sheet and sheet[f] is not None:
            # class 已在上面设过；若 sheet 里有就覆盖为原值（保持往返一致）
            out[f] = sheet[f]
    return out


_VALID_FORMATS = ("zen", "legacy")

# Sentinel: theme 参数缺省时使用内置默认主题；theme=None 表示不注入主题。
USE_DEFAULT_THEME = object()

# 默认主题：assets/default_theme.json。首次需要时懒加载。
_DEFAULT_THEME: dict | None = None
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_DEFAULT_THEME_FILE = _ASSETS_DIR / "default_theme.json"


def _load_default_theme() -> dict:
    """加载并返回默认主题 dict 的深拷贝（每次调用独立，id 后续会重生成）。"""
    global _DEFAULT_THEME
    if _DEFAULT_THEME is None:
        _DEFAULT_THEME = json.loads(_DEFAULT_THEME_FILE.read_text(encoding="utf-8"))
    # 深拷贝，避免调用方污染缓存
    return json.loads(json.dumps(_DEFAULT_THEME))


def _regenerate_theme_ids(theme: dict) -> dict:
    """重新生成 theme 内各子项的 id，避免跨文件 id 重复。

    XMind 用 theme 子项的 id 引用样式；同一组 id 出现在多个文件不会报错，
    但为干净起见每次写出生成新 id。
    """
    for k, v in theme.items():
        if isinstance(v, dict) and "id" in v:
            v["id"] = _new_id("th")
    return theme


def _normalize_format(fmt: str | None) -> str:
    """规范化 format 参数，返回 'zen' 或 'legacy'。None 默认 'zen'。"""
    if fmt is None:
        return "zen"
    norm = fmt.lower()
    if norm not in _VALID_FORMATS:
        raise ValueError(
            f"不支持的格式: {fmt!r}。可选: {list(_VALID_FORMATS)}"
        )
    return norm


def write_xmind(
    sheets: list[dict],
    file_path: PathLike,
    *,
    format: str | None = None,
    theme=USE_DEFAULT_THEME,
) -> str:
    """把 sheets 列表写入 .xmind 文件，返回绝对路径。

    Parameters
    ----------
    sheets : list[dict]
        每个 sheet dict 必须有 ``title`` 和 ``topic`` 字段。topic 可以嵌套 ``topics``。
    file_path : str | Path
        输出 .xmind 文件路径。
    format : str | None
        输出格式：``'zen'``（默认，XMind 8+/Zen/2020+，content.json）或
        ``'legacy'``（XMind 8 兼容，content.xml）。legacy 时 theme 被忽略。
    theme
        主题：缺省（``USE_DEFAULT_THEME``）注入内置美观默认主题；
        传入 dict 用自定义主题；``None`` 不注入主题（朴素）。

    Returns
    -------
    str
        输出文件的绝对路径。
    """
    return write_xmind_full(sheets, file_path, format=format, theme=theme)


def write_xmind_full(
    sheets: list[dict],
    file_path: PathLike,
    styles: dict | None = None,
    manifest: dict | None = None,
    *,
    format: str | None = None,
    theme=USE_DEFAULT_THEME,
) -> str:
    """把 sheets 写入 .xmind，可选注入 styles.json 和 manifest.json（Zen）。

    Parameters
    ----------
    sheets
        list[sheet_dict]
    file_path
        输出 .xmind 文件路径
    styles
        可选，styles.json 的 dict 内容（仅 Zen，会原样写入 zip）
    manifest
        可选，manifest.json 的 dict 内容（仅 Zen）
    format
        ``'zen'``（默认）或 ``'legacy'``。legacy 时 styles/manifest/theme 被忽略。
    theme
        主题：缺省注入内置默认主题；dict 用自定义；``None`` 不注入。

    Returns
    -------
    str
        输出文件的绝对路径。
    """
    if not sheets:
        raise ValueError("sheets 列表不能为空")

    out_path = Path(file_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = _normalize_format(format)
    if fmt == "legacy":
        return _write_legacy(sheets, out_path)
    return _write_zen(sheets, out_path, styles=styles, manifest=manifest, theme=theme)


def _write_zen(
    sheets: list[dict],
    out_path: Path,
    styles: dict | None,
    manifest: dict | None,
    theme=USE_DEFAULT_THEME,
) -> str:
    """以 Zen 格式写出 .xmind（content.json + metadata.json + manifest.json）。"""
    content = [_to_xmind_sheet(s) for s in sheets]

    # 主题注入：缺省用内置默认主题，None 不注入，dict 用自定义。
    # 每个 sheet 各注入一份独立 theme（id 重新生成），避免跨 sheet/文件 id 重复。
    if theme is not None:
        for sheet_obj in content:
            t = _load_default_theme() if theme is USE_DEFAULT_THEME else json.loads(json.dumps(theme))
            sheet_obj["theme"] = _regenerate_theme_ids(t)

    # metadata.json：dataStructureVersion/layoutEngineVersion 是 XMind 判断
    # 文件格式版本的关键字段，缺失会导致 XMind 报 "not a valid XMind File"。
    metadata = {
        "dataStructureVersion": "3",
        "creator": {"name": "xmind_tool", "version": "0.4"},
        "layoutEngineVersion": "5",
    }

    # manifest.json：XMind 用它校验文件完整性。用户未提供则写一份默认的，
    # 列出标准内容条目。
    if manifest is None:
        manifest = {
            "file-entries": {
                "content.json": {},
                "metadata.json": {},
            }
        }

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        if styles is not None:
            zf.writestr("styles.json", json.dumps(styles, ensure_ascii=False))

    return str(out_path.resolve())


# ============================================================
# Legacy 格式 (XMind 8, content.xml)
# ============================================================

_CONTENT_NS = "urn:xmind:xmap:xmlns:content:2.0"
_MANIFEST_NS = "urn:xmind:xmap:xmlns:manifest:1.0"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_XLINK_HREF = f"{{{_XLINK_NS}}}href"


def _ctag(local: str) -> str:
    """content 命名空间的限定元素名。"""
    return f"{{{_CONTENT_NS}}}{local}"


def _topic_to_legacy_xml(parent: ET.Element, topic: dict, ts: str) -> None:
    """把 topic dict 写为 Legacy XML 的 <topic> 子树，挂到 parent。"""
    elem = ET.SubElement(parent, _ctag("topic"))
    elem.set("id", _new_id("t"))
    elem.set("timestamp", ts)

    title = ET.SubElement(elem, _ctag("title"))
    title.text = topic.get("title", "")

    note = topic.get("note")
    if note:
        notes_e = ET.SubElement(elem, _ctag("notes"))
        plain_e = ET.SubElement(notes_e, _ctag("plain"))
        plain_e.text = note

    labels = topic.get("labels") or []
    if labels:
        labels_e = ET.SubElement(elem, _ctag("labels"))
        for lbl in labels:
            le = ET.SubElement(labels_e, _ctag("label"))
            le.text = lbl

    link = topic.get("link")
    if link:
        elem.set(_XLINK_HREF, link)

    makers = topic.get("makers") or []
    if makers:
        mrefs = ET.SubElement(elem, _ctag("marker-refs"))
        for mid in makers:
            mref = ET.SubElement(mrefs, _ctag("marker-ref"))
            mref.set("marker-id", mid)

    children = topic.get("topics") or []
    if children:
        children_e = ET.SubElement(elem, _ctag("children"))
        topics_e = ET.SubElement(children_e, _ctag("topics"))
        topics_e.set("type", "attached")
        for child in children:
            _topic_to_legacy_xml(topics_e, child, ts)


def _write_legacy(sheets: list[dict], out_path: Path) -> str:
    """以 Legacy (XMind 8) 格式写出 .xmind（content.xml + META-INF/manifest.xml）。

    summary/detached/callout 在 XMind 8 的 content.xml 里用独立元素表示，但
    xmindparser 的 legacy reader 不读这些结构，做 roundtrip 会丢，故此处不写——
    仅保证 title 树 + note/labels/makers/link 可往返。
    """
    ET.register_namespace("", _CONTENT_NS)
    ET.register_namespace("xlink", _XLINK_NS)

    root = ET.Element(_ctag("xmap-content"))
    root.set("version", "2.0")
    ts = str(int(time.time() * 1000))

    for sheet in sheets:
        if "title" not in sheet:
            raise ValueError("每个 sheet 必须有 'title' 字段")
        if "topic" not in sheet:
            raise ValueError("每个 sheet 必须有 'topic' 字段（根节点）")

        sheet_e = ET.SubElement(root, _ctag("sheet"))
        sheet_e.set("id", sheet.get("id") or _new_id("s"))
        sheet_e.set("timestamp", ts)
        _topic_to_legacy_xml(sheet_e, sheet["topic"], ts)
        title_e = ET.SubElement(sheet_e, _ctag("title"))
        title_e.text = sheet["title"]

    manifest_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<manifest xmlns="{_MANIFEST_NS}">\n'
        '  <file-entry full-path="content.xml" media-type="text/xml"/>\n'
        '  <file-entry full-path="META-INF/" media-type=""/>\n'
        '  <file-entry full-path="META-INF/manifest.xml" media-type="text/xml"/>\n'
        '</manifest>'
    )

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        buf = io.BytesIO()
        tree = ET.ElementTree(root)
        tree.write(buf, encoding="UTF-8", xml_declaration=True)
        zf.writestr("content.xml", buf.getvalue())
        zf.writestr("META-INF/manifest.xml", manifest_xml)

    return str(out_path.resolve())
