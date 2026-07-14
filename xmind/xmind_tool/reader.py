"""
xmind_tool.reader: 读取 .xmind 文件为标准化的 dict 结构。

两种格式：
- XMind 8+ (Zen): content.json —— 自解析，完整保留 attached/detached/summary/callout
- XMind 7 (legacy): content.xml —— 回退到 xmindparser

为什么 Zen 不直接用 xmindparser：
  xmindparser 的 zenreader 只递归 children.attached，会静默丢弃
  概要框(summary)、游离主题(detached)、标注(callout)的标题内容。
  本模块自解析 content.json 以补全这些结构。

返回结构（每个 topic dict）::

    {
        "title": "...",
        "id": "...",             # 可选，原 id（往返保真用）
        "note": "...",            # 可选
        "labels": [...],          # 可选
        "makers": [...],          # 可选
        "link": "...",            # 可选
        "callout": [...],         # 可选，标注框（字符串列表，与 xmindparser 一致）
        "topics": [...],          # attached 子主题
        "summary": [...],         # 概要框（topic dict 列表，新增）
        "detached": [...],       # 游离主题（topic dict 列表，新增）
        # 以下为鲁棒性补全（v0.7.0）：原样透传，不解释
        "image": {...},           # 可选，{src,width,height,align?}
        "boundaries": [...],      # 可选，视觉分组框 [{id,title,range,...}]
        "extensions": [...],      # 可选，插件不透明数据
        "customWidth": ...,        # 可选，手动宽度
        "width": ...,             # 可选
        "position": {...},        # 可选，手动坐标
        "style": {...},           # 可选，节点级样式（如加粗）
    }

设计原则：JSON 通道（xmind→json/yaml）是 LLM 消费的主通道，必须无损。
reader 把 XMind Zen 的所有非结构化键原样读出，由 writer 原样写回；
只有 md 通道（xmind→md）按约定有损（视觉/布局不渲染为文本）。
"""

# topic 上原样透传的键（不解释、不递归，直接保留）。
# 这些是真实 XMind Zen 文件里普遍存在但 reader 之前静默丢弃的特征：
#   - image: 嵌入图片引用（src/width/height/align）
#   - boundaries: 视觉分组框
#   - extensions: 插件不透明数据
#   - customWidth/width/position: 布局状态
# 透传而非解释，是因为它们的语义就是"原样存在"，往返保真即可。
# style 已单独处理（在 _parse_topic 主体里），不在此列以免重复。
_TOPIC_PASSTHROUGH_KEYS = (
    "image", "boundaries", "extensions",
    "customWidth", "width", "position",
    "titleUnedited",
)
import json
from pathlib import Path
from typing import Union
from zipfile import ZipFile

from xmindparser import xmind_to_dict

PathLike = Union[str, Path]


def _is_zen(file_path: PathLike) -> bool:
    """是否为 XMind Zen 格式（含 content.json）。"""
    with ZipFile(str(file_path)) as zf:
        return "content.json" in zf.namelist()


def _plain_title(node: dict) -> str:
    """从 topic 取标题。优先 title，缺失时从 attributedTitle 富文本拼接。"""
    title = node.get("title")
    if title:
        return title
    at = node.get("attributedTitle")
    if at is None:
        return ""
    if isinstance(at, str):
        return at
    if isinstance(at, list):
        # [{"text": "C2："}, {"text": "宣语/"}, ...]
        parts = []
        for seg in at:
            if isinstance(seg, dict):
                parts.append(seg.get("text", ""))
            elif isinstance(seg, str):
                parts.append(seg)
        return "".join(parts)
    return ""


def _parse_topic(node: dict) -> dict:
    """把 XMind Zen content.json 的一个 topic 节点转为标准化 dict。"""
    out: dict = {"title": _plain_title(node)}

    # id：保留原 id。relationships 的 end1Id/end2Id 通过 topic id 关联，
    # 若 reader 丢弃 id，writer 重生成后连线端点会全部悬空。
    tid = node.get("id")
    if tid:
        out["id"] = tid

    # notes（XMind Zen: notes.plain.content）
    notes = node.get("notes")
    if isinstance(notes, dict):
        plain = notes.get("plain")
        if isinstance(plain, dict) and plain.get("content"):
            out["note"] = plain["content"]

    # labels
    labels = node.get("labels")
    if isinstance(labels, list) and labels:
        ls = []
        for lb in labels:
            if isinstance(lb, dict) and lb.get("content"):
                ls.append(lb["content"])
            elif isinstance(lb, str):
                ls.append(lb)
        if ls:
            out["labels"] = ls

    # makers / markers
    markers = node.get("markers")
    if isinstance(markers, list) and markers:
        ms = []
        for mk in markers:
            if isinstance(mk, dict) and mk.get("markerId"):
                ms.append(mk["markerId"])
        if ms:
            out["makers"] = ms

    # link (href)
    href = node.get("href")
    if href:
        out["link"] = href

    # style（节点级样式，如加粗 fo:font-weight）。
    # XMind 把视觉样式藏在 topic.style.properties 里，不在 title 文本中。
    # 这里原样保留整个 style dict，让 JSON 通道不丢视觉样式（md 通道不渲染）。
    style = node.get("style")
    if isinstance(style, dict) and style:
        out["style"] = style

    # 透传键：image/boundaries/extensions/customWidth/width/position 等真实文件
    # 普遍存在、但语义就是"原样存在"的非结构化特征。原样保留，让 JSON 通道
    # 无损、xmind→xmind 往返保真（md 通道不渲染这些视觉/布局状态）。
    for k in _TOPIC_PASSTHROUGH_KEYS:
        v = node.get(k)
        if v is None:
            continue
        # 空容器不读（避免 dict 里堆 None/[]）
        if isinstance(v, (list, dict)) and not v:
            continue
        out[k] = v

    children = node.get("children")
    if isinstance(children, dict):
        # attached 子主题
        attached = children.get("attached")
        if isinstance(attached, list) and attached:
            out["topics"] = [_parse_topic(c) for c in attached]

        # 标注框（callout）：保留为字符串列表，与 xmindparser 语义一致
        callouts = children.get("callout")
        if isinstance(callouts, list) and callouts:
            cs = [_plain_title(c) for c in callouts]
            cs = [c for c in cs if c]
            if cs:
                out["callout"] = cs

        # 游离主题（detached）：浮动独立主题
        detached = children.get("detached")
        if isinstance(detached, list) and detached:
            out["detached"] = [_parse_topic(c) for c in detached]

        # 概要框（summary）
        # XMind Zen 用两处存储概要框：
        #   1. children.summary[] —— 概要文本 topic（{id, title}）
        #   2. topic 顶层 summaries[]（children 的兄弟键）—— {id, range, topicId}
        # range 如 "(0,5)" 表示括住第 0~4 个 attached 子节点（半开区间 [0,5)）。
        # range 通过 topicId 关联到 children.summary 里的 topic。读取时把 range
        # 合并到对应 summary topic dict 的 "range" 字段，供渲染/回写使用。
        summaries = children.get("summary")
        if isinstance(summaries, list) and summaries:
            collected: list[dict] = []
            id_to_idx: dict[str, int] = {}
            for s in summaries:
                if not isinstance(s, dict):
                    continue
                # 跳过「纯引用」summary：只有 {id, range, topicId} 之类引用键、
                # 被引 topic 不在本子树。判断依据是「没有任何实质内容」——
                # 即没有 title/attributedTitle/image/style/labels/note 等。
                # 注意 title="" 不算"有 title"，但 image/style 等存在就应保留
                # （真实文件 map.xmind 的 summary topic 就是 title 空但有 image）。
                has_title = bool(s.get("title") or s.get("attributedTitle"))
                has_content = has_title or any(
                    s.get(k) for k in
                    ("image", "style", "labels", "notes", "markers",
                     "children", "extensions", "boundaries")
                )
                if not has_content:
                    continue
                parsed = _parse_topic(s)
                # 兼容旧/非标准格式：range 直接挂在 topic 上
                if s.get("range"):
                    parsed["range"] = s["range"]
                if s.get("id"):
                    id_to_idx[s["id"]] = len(collected)
                collected.append(parsed)
            # 从 topic 顶层 summaries[] 按 topicId 合并 range（XMind 真实格式）
            summaries_meta = node.get("summaries")
            if isinstance(summaries_meta, list):
                for sm in summaries_meta:
                    if not isinstance(sm, dict):
                        continue
                    tid = sm.get("topicId")
                    if tid and tid in id_to_idx and sm.get("range"):
                        collected[id_to_idx[tid]]["range"] = sm["range"]
            if collected:
                out["summary"] = collected

    return out


def _read_zen(file_path: PathLike) -> list[dict]:
    """自解析 XMind Zen 的 content.json，返回 list[sheet_dict]。"""
    with ZipFile(str(file_path)) as zf:
        raw = json.loads(zf.read("content.json"))

    # sheet 级原样透传的键（非结构化、语义=原样存在）。
    # relationships（跨树连线）/legend（图例布局状态）等之前被静默丢弃，
    # 这里读出以保 JSON 通道无损、往返保真。
    _SHEET_PASSTHROUGH_KEYS = (
        "relationships", "legend", "topicPositioning", "class", "style",
    )

    sheets: list[dict] = []
    for s in raw:
        sheet = {
            "title": s.get("title", ""),
            "topic": _parse_topic(s.get("rootTopic", {})),
        }
        sid = s.get("id")
        if sid:
            sheet["id"] = sid
        structure = s.get("rootTopic", {}).get("structureClass")
        if structure:
            sheet["structure"] = structure
        # 透传 sheet 级非结构化键
        for k in _SHEET_PASSTHROUGH_KEYS:
            v = s.get(k)
            if v is None:
                continue
            if isinstance(v, (list, dict)) and not v:
                continue
            sheet[k] = v
        sheets.append(sheet)
    return sheets


def read_xmind(file_path: PathLike) -> list[dict]:
    """读取 .xmind 文件，返回 list[sheet_dict]。

    Zen 格式（content.json）由本模块自解析，完整保留概要框/游离主题/标注；
    老格式（content.xml）回退到 xmindparser。
    """
    if _is_zen(file_path):
        return _read_zen(file_path)
    return xmind_to_dict(str(file_path))


def read_xmind_full(file_path: PathLike) -> dict:
    """读取 .xmind 的完整内容，包括 styles.json 和 manifest.json（如果有）。

    Returns
    -------
    dict
        ``{"sheets": list[dict], "styles": dict, "manifest": dict}``
        styles 和 manifest 在文件缺失时为空 dict。
    """
    sheets = read_xmind(file_path)

    styles: dict = {}
    manifest: dict = {}
    with ZipFile(str(file_path)) as zf:
        names = zf.namelist()
        if "styles.json" in names:
            styles = json.loads(zf.read("styles.json"))
        if "manifest.json" in names:
            manifest = json.loads(zf.read("manifest.json"))

    return {"sheets": sheets, "styles": styles, "manifest": manifest}
