"""鲁棒性测试 — RED 阶段：用真实 XMind Zen 文件里观测到的结构，
验证 reader/writer 对之前静默丢弃的特征做到无损读写。

ground truth（来自对 110 个真实 .xmind 的 content.json 普查）：
- image: {src:"xap:resources/<hash>.png", width, height, align?} —— 616 topics
- boundaries: [{id, title:"", range:"(i,j)", style?, titleUnedited?}] —— 21 topics
- relationships: sheet 级 [{id, end1Id, end2Id, title?, controlPoints?}] —— 55 in 14 sheets
- extensions: opaque addon blob —— 109 topics
- legend: sheet 级 layout 状态 —— 9 sheets
- sheet.class / sheet.style / topicPositioning —— 多数 sheet 都有
- customWidth / width / position —— 2281 topics 的布局状态
- topic.id 必须保留 —— 否则 relationships 的 end1Id/end2Id 会悬空
- notes 的 html+ops+plain 富形态 —— 2 notes（plain 始终在，是文本真源）

设计原则（与 skill 一致）：
- JSON 通道（xmind→json/yaml）必须无损，因为是 LLM 消费的主通道。
- md 通道保持有损（视觉/布局不渲染为文本）。
- xmind→xmind 往返必须无损，否则用户编辑后存盘会丢数据。
"""
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

SAMPLES = Path(__file__).parent.parent / "samples"


def _write_zen(path: Path, content: list) -> None:
    """把 content.json list[sheet] 写成一个最小 Zen .xmind（含必需 metadata/manifest）。"""
    metadata = {"dataStructureVersion": "3",
                "creator": {"name": "test", "version": "0"},
                "layoutEngineVersion": "5"}
    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}}}
    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))


# ====================================================================
# image
# ====================================================================
class TestReaderImage(unittest.TestCase):
    """image：真实 XMind 用 {src, width, height, align?} 挂在 topic 上，
    src 形如 "xap:resources/<hash>.png"，图片字节实际在 zip 的 resources/ 下。

    reader 必须把 image 读进 topic dict（JSON 通道无损）。
    """

    def _make_xmind_with_image(self, path: Path) -> None:
        content = [{
            "id": "s1", "class": "sheet", "title": "带图",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "根",
                "children": {"attached": [{
                    "id": "t1", "class": "topic", "title": "带图节点",
                    "image": {
                        "src": "xap:resources/abc123.png",
                        "width": 343, "height": 207, "align": "right",
                    },
                }]},
            },
        }]
        _write_zen(path, content)

    def test_reader_preserves_image(self):
        from xmind_tool.reader import read_xmind
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "img.xmind"
            self._make_xmind_with_image(p)
            sheets = read_xmind(str(p))
        node = sheets[0]["topic"]["topics"][0]
        self.assertIn("image", node, "reader 必须读出 image")
        self.assertEqual(node["image"]["src"], "xap:resources/abc123.png")
        self.assertEqual(node["image"]["width"], 343)
        self.assertEqual(node["image"]["height"], 207)
        self.assertEqual(node["image"]["align"], "right")


# ====================================================================
# boundaries
# ====================================================================
class TestReaderBoundaries(unittest.TestCase):
    """boundaries：topic.children.attached 之上挂的视觉分组框。
    真实结构：[{id, title:"", range:"(i,j)", style?, titleUnedited?}]
    range 是字符串，"(0,2)" 表示括住第 0、1 个 attached 子节点。

    reader 必须读出 boundaries（含 range 字符串），writer 必须原样写回。
    """

    def _make_xmind_with_boundary(self, path: Path) -> None:
        content = [{
            "id": "s1", "class": "sheet", "title": "带分组框",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "根",
                "children": {"attached": [
                    {"id": "t1", "class": "topic", "title": "A"},
                    {"id": "t2", "class": "topic", "title": "B"},
                    {"id": "t3", "class": "topic", "title": "C"},
                ]},
                "boundaries": [{
                    "id": "b1",
                    "title": "",
                    "range": "(0,2)",
                }],
            },
        }]
        _write_zen(path, content)

    def test_reader_preserves_boundaries(self):
        from xmind_tool.reader import read_xmind
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "bnd.xmind"
            self._make_xmind_with_boundary(p)
            sheets = read_xmind(str(p))
        root = sheets[0]["topic"]
        self.assertIn("boundaries", root, "reader 必须读出 boundaries")
        self.assertEqual(len(root["boundaries"]), 1)
        b = root["boundaries"][0]
        self.assertEqual(b["id"], "b1")
        self.assertEqual(b["range"], "(0,2)")

    def test_writer_roundtrips_boundaries(self):
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "bnd.xmind"
            self._make_xmind_with_boundary(src)
            sheets = read_xmind(str(src))
            out = Path(tmp) / "bnd_rt.xmind"
            write_xmind(sheets, str(out), theme=None)
            sheets2 = read_xmind(str(out))
        root = sheets2[0]["topic"]
        self.assertIn("boundaries", root, "writer 必须写回 boundaries")
        self.assertEqual(root["boundaries"][0]["range"], "(0,2)")


# ====================================================================
# relationships (sheet-level cross-tree edges)
# ====================================================================
class TestReaderRelationships(unittest.TestCase):
    """relationships：sheet 级的跨树连线，真实结构：
    [{id, end1Id, end2Id, title?, controlPoints?}]
    end1Id/end2Id 是 topic id。这是有语义的结构（A--label-->B），
    不是纯布局，必须读出且可往返。
    """

    def _make_xmind_with_relationship(self, path: Path) -> None:
        content = [{
            "id": "s1", "class": "sheet", "title": "带连线",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "根",
                "children": {"attached": [
                    {"id": "t1", "class": "topic", "title": "A"},
                    {"id": "t2", "class": "topic", "title": "B"},
                ]},
            },
            "relationships": [{
                "id": "rel1",
                "end1Id": "t1",
                "end2Id": "t2",
                "title": "改进",
            }],
        }]
        _write_zen(path, content)

    def test_reader_preserves_relationships(self):
        from xmind_tool.reader import read_xmind
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "rel.xmind"
            self._make_xmind_with_relationship(p)
            sheets = read_xmind(str(p))
        sheet = sheets[0]
        self.assertIn("relationships", sheet, "reader 必须读出 relationships")
        self.assertEqual(len(sheet["relationships"]), 1)
        r = sheet["relationships"][0]
        self.assertEqual(r["end1Id"], "t1")
        self.assertEqual(r["end2Id"], "t2")
        self.assertEqual(r["title"], "改进")


# ====================================================================
# id preservation (critical: relationships dangle without it)
# ====================================================================
class TestIdPreservation(unittest.TestCase):
    """topic.id 必须在 reader 读出且 writer 写回时保留原值。

    现状：writer 对每个 topic 都重新生成 id（_new_id("t")），导致
    xmind→xmind 往返后 relationships 的 end1Id/end2Id 全部悬空。
    这是 relationship 保真的前提。
    """

    def test_reader_preserves_topic_id(self):
        from xmind_tool.reader import read_xmind
        content = [{
            "id": "s1", "class": "sheet", "title": "T",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "根",
                "children": {"attached": [
                    {"id": "child-abc", "class": "topic", "title": "子"},
                ]},
            },
        }]
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "id.xmind"
            _write_zen(p, content)
            sheets = read_xmind(str(p))
        root = sheets[0]["topic"]
        self.assertEqual(root.get("id"), "r1", "reader 必须保留 root id")
        child = root["topics"][0]
        self.assertEqual(child.get("id"), "child-abc", "reader 必须保留子节点 id")

    def test_writer_preserves_topic_id_on_roundtrip(self):
        """读→写→读后，原 id 必须仍在（不重新生成）。"""
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        content = [{
            "id": "s1", "class": "sheet", "title": "T",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "根",
                "children": {"attached": [
                    {"id": "child-abc", "class": "topic", "title": "子"},
                ]},
            },
        }]
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "id.xmind"
            _write_zen(src, content)
            sheets = read_xmind(str(src))
            out = Path(tmp) / "id_rt.xmind"
            write_xmind(sheets, str(out), theme=None)
            sheets2 = read_xmind(str(out))
        child = sheets2[0]["topic"]["topics"][0]
        self.assertEqual(child.get("id"), "child-abc",
                         "writer 必须保留原 id，不能重新生成")

    def test_relationship_survives_roundtrip(self):
        """端到端：relationships 的 end1Id/end2Id 在往返后仍指向有效 topic id。"""
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "rel.xmind"
            self._make_rel(src)
            sheets = read_xmind(str(src))
            out = Path(tmp) / "rel_rt.xmind"
            write_xmind(sheets, str(out), theme=None)
            sheets2 = read_xmind(str(out))
        sheet = sheets2[0]
        ids = set()

        def collect(t):
            if isinstance(t, dict):
                if t.get("id"):
                    ids.add(t["id"])
                for c in t.get("topics") or []:
                    collect(c)

        collect(sheet["topic"])
        self.assertIn("relationships", sheet)
        r = sheet["relationships"][0]
        self.assertIn(r["end1Id"], ids, "end1Id 往返后必须指向有效 topic id")
        self.assertIn(r["end2Id"], ids, "end2Id 往返后必须指向有效 topic id")

    @staticmethod
    def _make_rel(path: Path) -> None:
        content = [{
            "id": "s1", "class": "sheet", "title": "带连线",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "根",
                "children": {"attached": [
                    {"id": "t1", "class": "topic", "title": "A"},
                    {"id": "t2", "class": "topic", "title": "B"},
                ]},
            },
            "relationships": [{
                "id": "rel1", "end1Id": "t1", "end2Id": "t2", "title": "改进",
            }],
        }]
        _write_zen(path, content)


# ====================================================================
# extensions (opaque addon blobs)
# ====================================================================
class TestReaderExtensions(unittest.TestCase):
    """extensions：XMind 插件/addon 存的不透明数据块（109 个真实 topic）。
    reader/writer 不解释它，但要原样透传，否则带插件的脑图往返会丢插件状态。
    """

    def _make_xmind_with_extensions(self, path: Path) -> None:
        content = [{
            "id": "s1", "class": "sheet", "title": "T",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "根",
                "children": {"attached": [
                    {"id": "t1", "class": "topic", "title": "带插件",
                     "extensions": [{"provider": "com.example.addon",
                                     "content": "opaque"}]},
                ]},
            },
        }]
        _write_zen(path, content)

    def test_reader_preserves_extensions(self):
        from xmind_tool.reader import read_xmind
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "ext.xmind"
            self._make_xmind_with_extensions(p)
            sheets = read_xmind(str(p))
        node = sheets[0]["topic"]["topics"][0]
        self.assertIn("extensions", node, "reader 必须读出 extensions")
        self.assertEqual(node["extensions"][0]["provider"], "com.example.addon")

    def test_writer_roundtrips_extensions(self):
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "ext.xmind"
            self._make_xmind_with_extensions(src)
            sheets = read_xmind(str(src))
            out = Path(tmp) / "ext_rt.xmind"
            write_xmind(sheets, str(out), theme=None)
            sheets2 = read_xmind(str(out))
        node = sheets2[0]["topic"]["topics"][0]
        self.assertIn("extensions", node, "writer 必须写回 extensions")


# ====================================================================
# sheet-level keys: legend / class / style / topicPositioning
# ====================================================================
class TestReaderSheetLevelKeys(unittest.TestCase):
    """sheet 上的非结构键：legend（图例布局状态）、class、style、topicPositioning。
    真实文件普遍有这些。reader 必须读出，writer 必须回写。
    """

    def _make_xmind_with_sheet_keys(self, path: Path) -> None:
        content = [{
            "id": "s1", "class": "sheet", "title": "T",
            "rootTopic": {"id": "r1", "class": "topic", "title": "根"},
            "legend": {"visibility": "hidden",
                       "position": {"x": 100.0, "y": 200.0}},
            "topicPositioning": "free",
            "style": {"id": "ss1", "properties": {"svg:fill": "#fff"}},
        }]
        _write_zen(path, content)

    def test_reader_preserves_sheet_legend(self):
        from xmind_tool.reader import read_xmind
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "leg.xmind"
            self._make_xmind_with_sheet_keys(p)
            sheets = read_xmind(str(p))
        sheet = sheets[0]
        self.assertIn("legend", sheet)
        self.assertEqual(sheet["legend"]["visibility"], "hidden")

    def test_reader_preserves_sheet_class(self):
        from xmind_tool.reader import read_xmind
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "leg.xmind"
            self._make_xmind_with_sheet_keys(p)
            sheets = read_xmind(str(p))
        self.assertEqual(sheets[0].get("class"), "sheet")

    def test_reader_preserves_sheet_style(self):
        from xmind_tool.reader import read_xmind
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "leg.xmind"
            self._make_xmind_with_sheet_keys(p)
            sheets = read_xmind(str(p))
        self.assertIn("style", sheets[0])
        self.assertEqual(sheets[0]["style"]["properties"]["svg:fill"], "#fff")


# ====================================================================
# layout keys: customWidth / width / position
# ====================================================================
class TestReaderLayoutKeys(unittest.TestCase):
    """布局状态键：customWidth（2078）、width（207）、position（34）。
    不解释，原样透传即可，但必须不丢。
    """

    def _make_xmind_with_layout(self, path: Path) -> None:
        content = [{
            "id": "s1", "class": "sheet", "title": "T",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "根",
                "children": {"attached": [
                    {"id": "t1", "class": "topic", "title": "布局节点",
                     "customWidth": 200, "width": 180,
                     "position": {"x": 100.0, "y": 50.0}},
                ]},
            },
        }]
        _write_zen(path, content)

    def test_reader_preserves_layout_keys(self):
        from xmind_tool.reader import read_xmind
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "lay.xmind"
            self._make_xmind_with_layout(p)
            sheets = read_xmind(str(p))
        node = sheets[0]["topic"]["topics"][0]
        self.assertEqual(node.get("customWidth"), 200)
        self.assertEqual(node.get("width"), 180)
        self.assertEqual(node.get("position"), {"x": 100.0, "y": 50.0})

    def test_writer_roundtrips_layout_keys(self):
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "lay.xmind"
            self._make_xmind_with_layout(src)
            sheets = read_xmind(str(src))
            out = Path(tmp) / "lay_rt.xmind"
            write_xmind(sheets, str(out), theme=None)
            sheets2 = read_xmind(str(out))
        node = sheets2[0]["topic"]["topics"][0]
        self.assertEqual(node.get("customWidth"), 200, "writer 必须写回 customWidth")
        self.assertEqual(node.get("position"), {"x": 100.0, "y": 50.0})


# ====================================================================
# real-file smoke: zero silent-drop on a rich real file
# ====================================================================
class TestRealFileNoSilentDrop(unittest.TestCase):
    """对一个真实文件做 read→write→read，断言关键特征计数不下降。

    这是对"静默丢弃"回归的保护网：任何特征在往返后数量变少就是失败。
    用一个真实存在的含 image+boundaries+relationships+extensions 的文件。
    """
    REAL = Path(r"C:\Users\Breeze\ZCodeProject\xmind_robustness\_tmp_cs"
                r"\操作系统\计算机操作系统.xmind")

    def test_roundtrip_preserves_feature_counts(self):
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        if not self.REAL.exists():
            self.skipTest(f"真实文件不存在: {self.REAL}")
        sheets1 = read_xmind(str(self.REAL))
        c1 = self._count_features(sheets1)
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "real_rt.xmind"
            write_xmind(sheets1, str(out), theme=None)
            sheets2 = read_xmind(str(out))
        c2 = self._count_features(sheets2)
        for feat, n1 in c1.items():
            n2 = c2.get(feat, 0)
            self.assertEqual(n2, n1,
                             f"往返后 {feat} 数量下降: {n1} -> {n2}")

    @staticmethod
    def _count_features(sheets) -> dict:
        c = {"topics": 0, "images": 0, "boundaries": 0,
             "relationships": 0, "extensions": 0, "styles": 0,
             "markers": 0, "notes": 0, "summaries": 0, "detached": 0}

        def walk(t):
            if not isinstance(t, dict):
                return
            c["topics"] += 1
            if t.get("image"):
                c["images"] += 1
            if t.get("boundaries"):
                c["boundaries"] += len(t["boundaries"])
            if t.get("extensions"):
                c["extensions"] += 1
            if t.get("style"):
                c["styles"] += 1
            if t.get("markers"):
                c["markers"] += 1
            if t.get("notes") or t.get("note"):
                c["notes"] += 1
            if t.get("summary"):
                c["summaries"] += len(t["summary"])
            if t.get("detached"):
                c["detached"] += len(t["detached"])
            for ch in t.get("topics") or []:
                walk(ch)
            for ch in t.get("summary") or []:
                walk(ch)
            for ch in t.get("detached") or []:
                walk(ch)

        for s in sheets:
            if s.get("relationships"):
                c["relationships"] += len(s["relationships"])
            if s.get("topic"):
                walk(s["topic"])
        return c


def _find_real_file(*rels: str) -> Path:
    """在已知克隆位置下找一个真实 .xmind；找不到返回缺失路径（让测试 skip）。"""
    base = Path(r"C:\Users\Breeze\ZCodeProject\xmind_robustness")
    cands = []
    for rel in rels:
        # 尝试 cs / psy 两个克隆根
        for root in (base / "_tmp_cs", base / "_tmp_psy"):
            cands.append(root / rel)
    for c in cands:
        if c.exists():
            return c
    return cands[0] if cands else base / "missing.xmind"


class TestRealFileImageRoundtrip(unittest.TestCase):
    """真实文件含大量 image（Psyduck 的 shared_ptr 有图）：往返后 image 计数不下降。"""
    REAL = _find_real_file("C++/smart-ptr/3. shared_ptr.xmind")

    def test_image_count_preserved(self):
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        if not self.REAL.exists():
            self.skipTest(f"真实文件不存在: {self.REAL}")
        s1 = read_xmind(str(self.REAL))

        def count_images(t):
            n = 1 if (isinstance(t, dict) and t.get("image")) else 0
            if isinstance(t, dict):
                for c in (t.get("topics") or []) + (t.get("summary") or []) \
                         + (t.get("detached") or []):
                    n += count_images(c)
            return n
        n1 = sum(count_images(s.get("topic", {})) for s in s1)
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "img_rt.xmind"
            write_xmind(s1, str(out), theme=None)
            s2 = read_xmind(str(out))
        n2 = sum(count_images(s.get("topic", {})) for s in s2)
        self.assertEqual(n2, n1, f"image 往返丢失: {n1} -> {n2}")


class TestSummaryTopicWithImageNoTitle(unittest.TestCase):
    """summary topic 可能只有 image、title 为空（真实文件 map.xmind 就这样）。

    现状 reader 的 summary 分支把「title 为空」当作「纯引用 {id,range,topicId}」
    跳过，导致 summary topic 上的 image/style 等被静默丢弃。这是真实数据触发的 bug。
    修复方向：只在 topic 既无 title 又无任何内容（image/style/labels/...）且只有
    引用键时才跳过；有 image 就该保留。
    """

    def _make_xmind_with_image_only_summary(self, path: Path) -> None:
        # summary topic: title 为空，但有 image
        content = [{
            "id": "s1", "class": "sheet", "title": "T",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "根",
                "children": {
                    "attached": [
                        {"id": "a1", "class": "topic", "title": "A"},
                        {"id": "a2", "class": "topic", "title": "B"},
                    ],
                    "summary": [
                        {"id": "sum1", "class": "topic", "title": "",
                         "image": {"src": "xap:resources/x.png",
                                   "width": 10, "height": 10}},
                    ],
                },
                "summaries": [{"id": "sm1", "range": "(0,2)",
                               "topicId": "sum1"}],
            },
        }]
        _write_zen(path, content)

    def test_reader_keeps_image_only_summary(self):
        from xmind_tool.reader import read_xmind
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "sumimg.xmind"
            self._make_xmind_with_image_only_summary(p)
            sheets = read_xmind(str(p))
        root = sheets[0]["topic"]
        self.assertIn("summary", root, "summary topic（哪怕 title 空）应被保留")
        self.assertEqual(len(root["summary"]), 1)
        s = root["summary"][0]
        self.assertIn("image", s, "summary topic 上的 image 不能丢")
        self.assertEqual(s["image"]["src"], "xap:resources/x.png")
        self.assertEqual(s.get("range"), "(0,2)")


if __name__ == "__main__":
    unittest.main()
