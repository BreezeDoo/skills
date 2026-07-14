"""Convert 模块测试 — RED 阶段。"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SAMPLES = Path(__file__).parent.parent / "samples"


class TestConvertTo(unittest.TestCase):
    """测试 .xmind → 其他格式。"""

    def test_xmind_to_json(self):
        """xmind_to 应能生成 .json 文件。"""
        from xmind_tool.convert import xmind_to

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            xmind_to(str(SAMPLES / "demo.xmind"), str(out), fmt="json")
            self.assertTrue(out.exists())
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertIsInstance(data, list)
            self.assertEqual(data[0]["title"], "示例脑图")
            self.assertEqual(data[0]["topic"]["title"], "中心主题")

    def test_xmind_to_yaml(self):
        """xmind_to 应能生成 .yaml 文件。"""
        from xmind_tool.convert import xmind_to

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.yaml"
            xmind_to(str(SAMPLES / "demo.xmind"), str(out), fmt="yaml")
            self.assertTrue(out.exists())
            content = out.read_text(encoding="utf-8")
            self.assertIn("示例脑图", content)
            self.assertIn("中心主题", content)

    def test_xmind_to_markdown(self):
        """xmind_to 应能生成 .md 文件，包含层级标题。"""
        from xmind_tool.convert import xmind_to

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.md"
            xmind_to(str(SAMPLES / "demo.xmind"), str(out), fmt="md")
            content = out.read_text(encoding="utf-8")
            self.assertIn("# 示例脑图", content)
            self.assertIn("## 中心主题", content)
            self.assertIn("### 分支 1", content)
            self.assertIn("子节点 1.1", content)
            # 备注应作为引用块
            self.assertIn("> 分支1的备注", content)
            # 标签应展示
            self.assertIn("重要", content)

    def test_xmind_to_unsupported_fmt_raises(self):
        """不支持的 fmt 应抛 ValueError。"""
        from xmind_tool.convert import xmind_to

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.txt"
            with self.assertRaises(ValueError):
                xmind_to(str(SAMPLES / "demo.xmind"), str(out), fmt="docx")


class TestConvertFrom(unittest.TestCase):
    """测试其他格式 → .xmind。"""

    def test_json_to_xmind(self):
        """json_to_xmind 应能读 json 并写出 .xmind。"""
        from xmind_tool.convert import json_to_xmind
        from xmind_tool.reader import read_xmind

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.json"
            dst = Path(tmp) / "out.xmind"
            src.write_text(
                json.dumps([{
                    "title": "From JSON",
                    "topic": {
                        "title": "R",
                        "topics": [{"title": "C1"}, {"title": "C2"}],
                    },
                }], ensure_ascii=False),
                encoding="utf-8",
            )
            json_to_xmind(str(src), str(dst))
            self.assertTrue(dst.exists())
            rt = read_xmind(str(dst))
            self.assertEqual(rt[0]["title"], "From JSON")
            self.assertEqual(len(rt[0]["topic"]["topics"]), 2)

    def test_yaml_to_xmind(self):
        """yaml_to_xmind 应能读 yaml 并写出 .xmind。"""
        from xmind_tool.convert import yaml_to_xmind
        from xmind_tool.reader import read_xmind

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.yaml"
            dst = Path(tmp) / "out.xmind"
            src.write_text(
                "- title: From YAML\n  topic:\n    title: R\n    topics:\n      - title: C1\n",
                encoding="utf-8",
            )
            yaml_to_xmind(str(src), str(dst))
            rt = read_xmind(str(dst))
            self.assertEqual(rt[0]["title"], "From YAML")


if __name__ == "__main__":
    unittest.main()
