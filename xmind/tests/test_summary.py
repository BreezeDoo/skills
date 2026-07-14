"""概要框(summary) / 游离主题(detached) / 标注(callout) 的读写测试。

xmindparser 只递归 children.attached，导致概要框等结构丢失。
本测试验证技能自解析后这些结构能被完整读出、写出、并经 markdown 渲染。
"""
import json
import unittest
import zipfile
from pathlib import Path

SAMPLES = Path(__file__).parent.parent / "samples"
FIXTURE = SAMPLES / "summary_demo.xmind"


def _build_summary_fixture(path: Path) -> None:
    """构造一个含概要框 + 游离主题的 XMind Zen fixture（content.json）。

    按 XMind 真实存储形态：概要文本 topic 直接放在「被附属节点」的
    children.summary 数组里（带 id + title），而非 {id,range,topicId} 引用。
    """
    content = [{
        "id": "sheet-1",
        "class": "sheet",
        "title": "概要演示",
        "rootTopic": {
            "id": "root-1",
            "class": "topic",
            "title": "中心主题",
            "structureClass": "org.xmind.ui.map.clockwise",
            "children": {
                "attached": [
                    {
                        "id": "b1",
                        "class": "topic",
                        "title": "分支1",
                        "children": {
                            "attached": [
                                {"id": "b1c1", "class": "topic", "title": "叶子1"},
                                {"id": "b1c2", "class": "topic", "title": "叶子2"},
                                {"id": "b1c3", "class": "topic", "title": "叶子3"},
                            ],
                            # 概要框：XMind Zen 真实格式分两处存储——
                            #   1. children.summary[] 放概要文本 topic（{id, title}）
                            #   2. topic 顶层 summaries[]（children 的兄弟）放
                            #      {id, range, topicId}，range "(0,2)" 表示括住
                            #      第 0~1 个 attached 子节点（叶子1、叶子2）。
                            #      topicId 指回 children.summary 里的 topic。
                            "summary": [
                                {
                                    "id": "sum-topic-1",
                                    "title": "设计文件、代码、测试场景",
                                },
                            ],
                        },
                        # 概要框 range 引用表：children 的兄弟键
                        "summaries": [
                            {
                                "id": "sum-meta-1",
                                "range": "(0,2)",
                                "topicId": "sum-topic-1",
                            },
                        ],
                    },
                    {
                        "id": "b2",
                        "class": "topic",
                        "title": "分支2",
                        "children": {
                            # 游离主题（浮动的独立主题）
                            "detached": [
                                {"id": "dt-1", "class": "topic", "title": "游离想法"},
                            ],
                        },
                    },
                ],
            },
        },
    }]
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False))
        zf.writestr("metadata.json", json.dumps(
            {"creator": "test", "version": "1"}))


class TestSummaryRead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            _build_summary_fixture(FIXTURE)

    def test_summary_is_not_lost(self):
        """概要框标题必须被读出，不能因为只在 children.attached 递归而丢失。

        新 fixture 把概要框放在「分支1」下（XMind 真实存储形态：
        概要 topic 直接位于被附属节点的 children.summary 数组）。
        """
        from xmind_tool.reader import read_xmind
        sheets = read_xmind(str(FIXTURE))
        root = sheets[0]["topic"]
        self.assertEqual(root["title"], "中心主题")
        b1 = root["topics"][0]
        self.assertIn("summary", b1, "分支1 应包含概要框 summary 字段")
        self.assertEqual(
            [s["title"] for s in b1["summary"]],
            ["设计文件、代码、测试场景"],
        )

    def test_detached_is_not_lost(self):
        """游离主题必须被读出。"""
        from xmind_tool.reader import read_xmind
        sheets = read_xmind(str(FIXTURE))
        b2 = sheets[0]["topic"]["topics"][1]
        self.assertEqual(b2["title"], "分支2")
        self.assertIn("detached", b2)
        self.assertEqual([d["title"] for d in b2["detached"]], ["游离想法"])

    def test_root_has_no_spurious_summary(self):
        """根节点无概要框时不应被凭空加上 summary 字段。"""
        from xmind_tool.reader import read_xmind
        sheets = read_xmind(str(FIXTURE))
        root = sheets[0]["topic"]
        self.assertNotIn("summary", root)


class TestSummaryWriteAndRoundtrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            _build_summary_fixture(FIXTURE)

    def test_writer_preserves_summary(self):
        """写出的 .xmind 应保留 summary 结构，再读回时仍能取到。"""
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        import tempfile, os
        sheets = read_xmind(str(FIXTURE))
        out = os.path.join(tempfile.mkdtemp(), "rt.xmind")
        write_xmind(sheets, out)
        back = read_xmind(out)
        b1 = back[0]["topic"]["topics"][0]
        self.assertIn("summary", b1, "写回后分支1 应仍含 summary")
        self.assertEqual(
            [s["title"] for s in b1["summary"]],
            ["设计文件、代码、测试场景"],
        )

    def test_writer_preserves_detached(self):
        """写出的 .xmind 应保留 detached 结构，再读回时仍能取到。"""
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        import tempfile, os
        sheets = read_xmind(str(FIXTURE))
        out = os.path.join(tempfile.mkdtemp(), "rt3.xmind")
        write_xmind(sheets, out)
        back = read_xmind(out)
        b2 = back[0]["topic"]["topics"][1]
        self.assertIn("detached", b2, "写回后分支2 应仍含 detached")
        self.assertEqual([d["title"] for d in b2["detached"]], ["游离想法"])

    def test_roundtrip_summary_content_matches(self):
        """read -> write -> read 后，概要框内容一致。"""
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        import tempfile, os
        original = read_xmind(str(FIXTURE))
        out = os.path.join(tempfile.mkdtemp(), "rt2.xmind")
        write_xmind(original, out)
        reread = read_xmind(out)
        # summary 在 fixture 的分支1 下
        self.assertEqual(
            [s["title"] for s in original[0]["topic"]["topics"][0]["summary"]],
            [s["title"] for s in reread[0]["topic"]["topics"][0]["summary"]],
        )

    def test_roundtrip_preserves_range(self):
        """read -> write -> read 后，概要框的 range 也应保真。"""
        from xmind_tool.reader import read_xmind
        from xmind_tool.writer import write_xmind
        import tempfile, os
        original = read_xmind(str(FIXTURE))
        out = os.path.join(tempfile.mkdtemp(), "rt4.xmind")
        write_xmind(original, out)
        reread = read_xmind(out)
        orig_sum = original[0]["topic"]["topics"][0]["summary"][0]
        re_sum = reread[0]["topic"]["topics"][0]["summary"][0]
        self.assertEqual(orig_sum.get("range"), re_sum.get("range"))

    def test_writer_emits_top_level_summaries_array(self):
        """写出的 .xmind 必须含 topic 顶层 summaries[]（children 的兄弟键）。

        XMind Zen 真实格式：概要文本 topic 在 children.summary，而 range +
        topicId 引用在 topic 顶层 summaries[]。缺少 summaries[] 时 XMind 无法
        确定概要框括住哪些子节点，会把它渲染成游离主题而非括号 —— 这正是
        之前 "not a valid / 括号不对" 的根因。
        """
        from xmind_tool.writer import write_xmind
        from xmind_tool.reader import read_xmind
        import tempfile, os, json, zipfile
        sheets = read_xmind(str(FIXTURE))
        out = os.path.join(tempfile.mkdtemp(), "raw.xmind")
        write_xmind(sheets, out)
        with zipfile.ZipFile(out) as zf:
            raw = json.loads(zf.read("content.json"))
        # 定位到「分支1」节点（fixture 里唯一带概要框的）
        b1 = raw[0]["rootTopic"]["children"]["attached"][0]
        # children.summary 存在且只有 title（无 range 挂在 topic 上）
        self.assertIn("summary", b1["children"])
        sum_topic = b1["children"]["summary"][0]
        self.assertEqual(sum_topic["title"], "设计文件、代码、测试场景")
        self.assertNotIn("range", sum_topic, "range 不应挂在 topic 上")
        # 顶层 summaries[] 存在，range + topicId 链接正确
        self.assertIn("summaries", b1, "topic 顶层必须有 summaries[] 兄弟键")
        meta = b1["summaries"][0]
        self.assertEqual(meta["range"], "(0,2)")
        self.assertEqual(meta["topicId"], sum_topic["id"],
                         "topicId 必须指向 children.summary 里的 topic id")


class TestSummaryMarkdownRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            _build_summary_fixture(FIXTURE)

    def test_markdown_renders_summary(self):
        """转 markdown 时，概要框标题应出现在输出中。"""
        from xmind_tool.convert import xmind_to_markdown
        import tempfile, os
        md_path = os.path.join(tempfile.mkdtemp(), "out.md")
        xmind_to_markdown(str(FIXTURE), md_path)
        text = Path(md_path).read_text(encoding="utf-8")
        self.assertIn("设计文件、代码、测试场景", text)
        self.assertIn("[概要]", text)
        self.assertIn("游离想法", text)

    def test_markdown_summary_after_bracketed_children(self):
        """概要框应渲染在它括住的子节点之后，而非与第一个子节点并列。

        fixture 的「分支1」有 叶子1/叶子2/叶子3，概要 range=(0,2)
        括住叶子1、叶子2。故概要行应出现在叶子2之后、叶子3之前。
        """
        from xmind_tool.convert import xmind_to_markdown
        import tempfile, os
        md_path = os.path.join(tempfile.mkdtemp(), "out.md")
        xmind_to_markdown(str(FIXTURE), md_path)
        text = Path(md_path).read_text(encoding="utf-8")
        pos_leaf1 = text.find("叶子1")
        pos_leaf2 = text.find("叶子2")
        pos_leaf3 = text.find("叶子3")
        pos_summary = text.find("[概要]")
        self.assertGreater(pos_summary, pos_leaf2, "概要应在叶子2之后")
        self.assertLess(pos_summary, pos_leaf3, "概要应在叶子3之前（括号收尾于叶子2）")

    def test_markdown_to_xmind_restores_summary(self):
        """md → xmind 时，[概要]/[游离] 标记应还原为 summary/detached 结构。"""
        from xmind_tool.convert import markdown_to_xmind, xmind_to_markdown
        from xmind_tool.reader import read_xmind
        import tempfile, os
        # 先用 fixture 导出 md，再从 md 导回 xmind，验证 summary 还原
        md_path = os.path.join(tempfile.mkdtemp(), "in.md")
        xmind_to_markdown(str(FIXTURE), md_path)
        out_xmind = os.path.join(tempfile.mkdtemp(), "back.xmind")
        markdown_to_xmind(md_path, out_xmind)
        sheets = read_xmind(out_xmind)
        b1 = sheets[0]["topic"]["topics"][0]
        self.assertIn("summary", b1, "md→xmind 后分支1 应还原出 summary")
        self.assertEqual(
            [s["title"] for s in b1["summary"]],
            ["设计文件、代码、测试场景"],
        )
        b2 = sheets[0]["topic"]["topics"][1]
        self.assertIn("detached", b2, "md→xmind 后分支2 应还原出 detached")
        self.assertEqual([d["title"] for d in b2["detached"]], ["游离想法"])

    def test_md_to_xmind_infers_range_from_position(self):
        """[概要] 出现在子节点序列中间时，range 应括住它之前的全部子节点。

        md 形如「子A / 子B / [概要] / 子C」→ 概要括住 子A,子B → range (0,2)，
        子C 在括号外。这避免了「括住全部子节点」的满覆盖 range（XMind 不渲染
        满覆盖括号）。这是之前 md 往返「没有括号」bug 的回归测试。
        """
        from xmind_tool.convert import _parse_markdown
        from xmind_tool.writer import write_xmind
        import tempfile, os, json, zipfile
        md = "# 概要位置测试\n\n## 根\n\n### 父节点\n\n#### 子A\n\n#### 子B\n\n#### [概要] 概要文字\n\n#### 子C\n"
        sheets = _parse_markdown(md)
        parent = sheets[0]["topic"]["topics"][0]
        self.assertEqual([t["title"] for t in parent["topics"]], ["子A", "子B", "子C"])
        self.assertIn("summary", parent)
        self.assertEqual(parent["summary"][0]["title"], "概要文字")
        # [概要] 在 子A、子B 之后 → range (0,2)，子C 在括号外
        self.assertEqual(parent["summary"][0].get("range"), "(0,2)")
        # 写盘后 summaries[] 的 range 也要落到 (0,2)
        out = os.path.join(tempfile.mkdtemp(), "pos.xmind")
        write_xmind(sheets, out)
        with zipfile.ZipFile(out) as zf:
            raw = json.loads(zf.read("content.json"))
        p = raw[0]["rootTopic"]["children"]["attached"][0]
        self.assertEqual(p["summaries"][0]["range"], "(0,2)")
        self.assertEqual(
            p["summaries"][0]["topicId"],
            p["children"]["summary"][0]["id"],
        )


class TestSummaryCsvOpml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            _build_summary_fixture(FIXTURE)

    def test_csv_includes_summary_and_detached(self):
        """转 CSV 时，概要框与游离主题应各占一行。"""
        from xmind_tool.convert import xmind_to_csv
        import tempfile, os
        csv_path = os.path.join(tempfile.mkdtemp(), "out.csv")
        xmind_to_csv(str(FIXTURE), csv_path)
        text = Path(csv_path).read_text(encoding="utf-8")
        self.assertIn("设计文件、代码、测试场景", text)
        self.assertIn("[概要]", text)
        self.assertIn("游离想法", text)
        self.assertIn("[游离]", text)

    def test_opml_includes_summary_and_detached(self):
        """转 OPML 时，概要框与游离主题应作为带 _type 的 outline 出现。"""
        from xmind_tool.convert import xmind_to_opml
        import tempfile, os
        opml_path = os.path.join(tempfile.mkdtemp(), "out.opml")
        xmind_to_opml(str(FIXTURE), opml_path)
        text = Path(opml_path).read_text(encoding="utf-8")
        self.assertIn("设计文件、代码、测试场景", text)
        self.assertIn('summary', text)
        self.assertIn("游离想法", text)
        self.assertIn('detached', text)


if __name__ == "__main__":
    unittest.main()
