"""Reader 模块测试 — RED 阶段。"""
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

SAMPLES = Path(__file__).parent.parent / "samples"


class TestReadXmind(unittest.TestCase):
    def test_returns_list_of_sheets(self):
        """read_xmind 应返回 list，每个元素是一个 sheet dict。"""
        from xmind_tool.reader import read_xmind
        result = read_xmind(str(SAMPLES / "demo.xmind"))
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "示例脑图")

    def test_sheet_has_topic_tree(self):
        """sheet 应包含 'topic' 字段，且 topic 嵌套包含子节点。"""
        from xmind_tool.reader import read_xmind
        result = read_xmind(str(SAMPLES / "demo.xmind"))
        topic = result[0]["topic"]
        self.assertEqual(topic["title"], "中心主题")
        sub_titles = [t["title"] for t in topic["topics"]]
        self.assertEqual(sub_titles, ["分支 1", "分支 2", "分支 3"])

    def test_preserves_note_label_link(self):
        """note/label/link/marker 等元信息应被保留。"""
        from xmind_tool.reader import read_xmind
        result = read_xmind(str(SAMPLES / "demo.xmind"))
        sub1 = result[0]["topic"]["topics"][0]
        self.assertEqual(sub1["note"], "分支1的备注")
        leaf11 = sub1["topics"][0]
        self.assertEqual(leaf11["labels"], ["重要"])
        self.assertEqual(leaf11["makers"], ["priority-1"])
        leaf12 = sub1["topics"][1]
        self.assertEqual(leaf12["link"], "https://example.com")


class TestReaderStyleProperties(unittest.TestCase):
    """reader 应保留 topic 的 style.properties（如加粗 fo:font-weight）。

    真实 XMind 文件主干主题大量使用 style.properties.fo:font-weight=700 表达加粗，
    语义藏在 style 对象里而非 title 文本。当前 reader 完全丢弃 style，导致
    xmind→JSON 通道也丢视觉样式。本组要求 reader 至少把 style 读进 topic dict。
    """

    @staticmethod
    def _make_xmind_with_bold_topic(path: Path) -> None:
        """构造一个含 style.properties.fo:font-weight=700 的 xmind 文件。"""
        content = [{
            "id": "s1", "class": "sheet", "title": "T",
            "rootTopic": {
                "id": "r1", "class": "topic", "title": "中心",
                "children": {"attached": [{
                    "id": "t1", "class": "topic", "title": "加粗分支",
                    "style": {"id": "st1", "properties": {"fo:font-weight": "700"}},
                }]},
            },
        }]
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("content.json", json.dumps(content, ensure_ascii=False))
            zf.writestr("metadata.json", json.dumps({"dataStructureVersion": "3"}))
            zf.writestr("manifest.json", json.dumps({"file-entries": {"content.json": {}}}))

    def test_reader_preserves_style_properties(self):
        """含 style.properties 的 topic 应在 dict 里保留 style。"""
        from xmind_tool.reader import read_xmind

        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "styled.xmind"
            self._make_xmind_with_bold_topic(p)
            root = read_xmind(str(p))[0]["topic"]
            branch = root["topics"][0]
            self.assertEqual(branch["title"], "加粗分支")
            self.assertIn("style", branch)
            self.assertEqual(
                branch["style"]["properties"]["fo:font-weight"], "700"
            )


if __name__ == "__main__":
    unittest.main()
