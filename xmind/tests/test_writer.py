"""Writer 模块测试 — RED 阶段。"""
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

SAMPLES = Path(__file__).parent.parent / "samples"


class TestWriteXmind(unittest.TestCase):
    def test_write_minimal_sheet_then_read(self):
        """写入一个最小 sheet（仅 title + 根节点），再读回，应等价。"""
        from xmind_tool.writer import write_xmind
        from xmind_tool.reader import read_xmind

        sheets = [{
            "title": "最小脑图",
            "topic": {"title": "根"},
        }]

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "minimal.xmind"
            write_xmind(sheets, str(out))
            self.assertTrue(out.exists())
            self.assertTrue(zipfile.is_zipfile(out))

            roundtrip = read_xmind(str(out))
            self.assertEqual(roundtrip[0]["title"], "最小脑图")
            self.assertEqual(roundtrip[0]["topic"]["title"], "根")

    def test_write_nested_topics_then_read(self):
        """写入嵌套树，读回应保持原结构。"""
        from xmind_tool.writer import write_xmind
        from xmind_tool.reader import read_xmind

        sheets = [{
            "title": "嵌套",
            "topic": {
                "title": "根",
                "topics": [
                    {"title": "A", "topics": [
                        {"title": "A.1"},
                        {"title": "A.2"},
                    ]},
                    {"title": "B"},
                ],
            },
        }]

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested.xmind"
            write_xmind(sheets, str(out))
            roundtrip = read_xmind(str(out))
            topic = roundtrip[0]["topic"]
            self.assertEqual(topic["title"], "根")
            self.assertEqual(len(topic["topics"]), 2)
            self.assertEqual([t["title"] for t in topic["topics"]], ["A", "B"])
            self.assertEqual(
                [t["title"] for t in topic["topics"][0]["topics"]],
                ["A.1", "A.2"],
            )

    def test_write_preserves_note_label_link(self):
        """写入 note/label/link，读回应保留。"""
        from xmind_tool.writer import write_xmind
        from xmind_tool.reader import read_xmind

        sheets = [{
            "title": "元数据",
            "topic": {
                "title": "根",
                "topics": [
                    {
                        "title": "子",
                        "note": "一条备注",
                        "labels": ["L1", "L2"],
                        "link": "https://example.com",
                        "makers": ["priority-1"],
                    }
                ],
            },
        }]

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "meta.xmind"
            write_xmind(sheets, str(out))
            child = read_xmind(str(out))[0]["topic"]["topics"][0]
            self.assertEqual(child["note"], "一条备注")
            self.assertEqual(child["labels"], ["L1", "L2"])
            self.assertEqual(child["link"], "https://example.com")
            self.assertEqual(child["makers"], ["priority-1"])

    def test_written_file_is_valid_zip_with_content_json(self):
        """写出文件应是合法 zip，含 content.json 和 metadata.json。"""
        from xmind_tool.writer import write_xmind

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "check.xmind"
            write_xmind([{"title": "T", "topic": {"title": "R"}}], str(out))
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                self.assertIn("content.json", names)
                self.assertIn("metadata.json", names)
                content = json.loads(zf.read("content.json"))
                self.assertEqual(content[0]["title"], "T")

    def test_root_topic_has_structureClass(self):
        """写出的 rootTopic 必须含 structureClass，否则 XMind 无法渲染布局。

        reader 读到的 sheet["structure"] 应写回 rootTopic.structureClass；
        缺失时用默认 org.xmind.ui.map.clockwise。
        """
        from xmind_tool.writer import write_xmind

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "struct.xmind"
            # 不给 structure，应填默认
            write_xmind([{"title": "T", "topic": {"title": "R"}}], str(out))
            with zipfile.ZipFile(out) as zf:
                content = json.loads(zf.read("content.json"))
                self.assertEqual(
                    content[0]["rootTopic"]["structureClass"],
                    "org.xmind.ui.map.clockwise",
                )

            out2 = Path(tmp) / "struct2.xmind"
            # 给定 structure，应写回
            write_xmind(
                [{"title": "T", "structure": "org.xmind.ui.logic.right",
                  "topic": {"title": "R"}}],
                str(out2),
            )
            with zipfile.ZipFile(out2) as zf:
                content = json.loads(zf.read("content.json"))
                self.assertEqual(
                    content[0]["rootTopic"]["structureClass"],
                    "org.xmind.ui.logic.right",
                )


    def test_empty_sheets_raises(self):
        """sheets 列表为空应抛 ValueError。"""
        from xmind_tool.writer import write_xmind

        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_xmind([], str(Path(tmp) / "x.xmind"))

    def test_topic_without_title_raises(self):
        """topic 缺 title 字段应抛 ValueError。"""
        from xmind_tool.writer import write_xmind

        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_xmind(
                    [{"title": "S", "topic": {}}],
                    str(Path(tmp) / "x.xmind"),
                )

    def test_write_preserves_style_properties(self):
        """topic 的 style.properties（如加粗 fo:font-weight）写回应原样保留。

        这样 xmind→JSON→xmind 的无损往返才真正不丢视觉样式。
        """
        from xmind_tool.writer import write_xmind

        sheets = [{
            "title": "S",
            "topic": {
                "title": "根",
                "topics": [{
                    "title": "加粗分支",
                    "style": {"properties": {"fo:font-weight": "700"}},
                }],
            },
        }]
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "styled.xmind"
            write_xmind(sheets, str(out))
            with zipfile.ZipFile(out) as zf:
                content = json.loads(zf.read("content.json"))
                branch = content[0]["rootTopic"]["children"]["attached"][0]
                self.assertEqual(branch["title"], "加粗分支")
                self.assertEqual(
                    branch["style"]["properties"]["fo:font-weight"], "700"
                )


if __name__ == "__main__":
    unittest.main()
