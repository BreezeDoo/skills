"""Legacy (XMind 8, content.xml) 写支持测试 — RED 阶段。

Zen writer 只能产出 content.json 格式。本测试验证 write_xmind 在
--format legacy / format='legacy' 时能写出可被 xmindparser 读回的 content.xml
文件，覆盖标题树 + note/labels/makers/link 元数据。

注意：xmindparser 的 legacy reader 不返回 summary/detached，所以这些结构
不做 roundtrip 断言；只验证 title 树 + 标准元数据可往返。
"""
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


def _write_legacy(sheets, out_path):
    """调用被测 API：以 legacy 格式写出。具体函数签名见 writer.py。"""
    from xmind_tool.writer import write_xmind
    return write_xmind(sheets, out_path, format="legacy")


class TestLegacyWrite(unittest.TestCase):
    def test_writes_content_xml_not_content_json(self):
        """legacy 格式应写出 content.xml，而不是 content.json。"""
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "legacy.xmind"
            _write_legacy(
                [{"title": "S", "topic": {"title": "根"}}], str(out)
            )
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
            self.assertIn("content.xml", names)
            self.assertNotIn("content.json", names)

    def test_legacy_roundtrip_preserves_title_tree(self):
        """写出 legacy 后用 xmindparser 读回，标题树应保持。"""
        from xmind_tool.reader import read_xmind

        sheets = [{
            "title": "旧格式脑图",
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
            out = Path(tmp) / "legacy.xmind"
            _write_legacy(sheets, str(out))
            self.assertTrue(zipfile.is_zipfile(out))

            roundtrip = read_xmind(str(out))
            self.assertEqual(roundtrip[0]["title"], "旧格式脑图")
            topic = roundtrip[0]["topic"]
            self.assertEqual(topic["title"], "根")
            self.assertEqual(
                [t["title"] for t in topic["topics"]], ["A", "B"]
            )
            self.assertEqual(
                [t["title"] for t in topic["topics"][0]["topics"]],
                ["A.1", "A.2"],
            )

    def test_legacy_roundtrip_preserves_metadata(self):
        """legacy roundtrip 应保留 note/labels/makers/link。"""
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
            out = Path(tmp) / "legacy_meta.xmind"
            _write_legacy(sheets, str(out))
            child = read_xmind(str(out))[0]["topic"]["topics"][0]
            self.assertEqual(child["note"], "一条备注")
            self.assertEqual(child["labels"], ["L1", "L2"])
            self.assertEqual(child["link"], "https://example.com")
            self.assertEqual(child["makers"], ["priority-1"])

    def test_legacy_includes_manifest(self):
        """XMind 8 legacy 文件需含 META-INF/manifest.xml，否则 XMind 报无效。"""
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "legacy.xmind"
            _write_legacy([{"title": "S", "topic": {"title": "R"}}], str(out))
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
            self.assertIn("content.xml", names)
            self.assertIn("META-INF/manifest.xml", names)

    def test_default_format_is_zen(self):
        """不给 format 参数时，默认仍写 Zen（content.json）。"""
        from xmind_tool.writer import write_xmind

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "default.xmind"
            write_xmind([{"title": "S", "topic": {"title": "R"}}], str(out))
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
            self.assertIn("content.json", names)
            self.assertNotIn("content.xml", names)


if __name__ == "__main__":
    unittest.main()
