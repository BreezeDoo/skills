"""默认主题注入测试 — RED 阶段。

XMind 生成的文件默认没有 theme 字段，打开时是朴素白底黑字。
write_xmind 应在 Zen 格式下为每个 sheet 注入一个内置的好看默认主题，
让生成的图直接美观。theme 来自 assets/default_theme.json。
"""
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


class TestDefaultTheme(unittest.TestCase):
    def _read_content(self, xmind_path: Path) -> list:
        """读 content.json。"""
        with zipfile.ZipFile(xmind_path) as zf:
            return json.loads(zf.read("content.json"))

    def test_zen_write_injects_default_theme(self):
        """Zen 写出应自动注入默认 theme，每个 sheet 带 theme 字段。"""
        from xmind_tool.writer import write_xmind

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "themed.xmind"
            write_xmind([{"title": "T", "topic": {"title": "R"}}], str(out))
            content = self._read_content(out)
            self.assertIn("theme", content[0], msg="Zen 输出缺少 theme 字段")
            theme = content[0]["theme"]
            self.assertIn("centralTopic", theme)
            self.assertIn("mainTopic", theme)
            self.assertIn("map", theme)

    def test_default_theme_has_colors(self):
        """默认主题的 map.properties 应含彩色 color-list，不是朴素黑字。"""
        from xmind_tool.writer import write_xmind

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "themed.xmind"
            write_xmind([{"title": "T", "topic": {"title": "R"}}], str(out))
            theme = self._read_content(out)[0]["theme"]
            props = theme["map"]["properties"]
            self.assertIn("color-list", props)
            # 彩色：应至少含多个不同 hex 色
            colors = props["color-list"].split()
            self.assertGreater(len(colors), 2, msg="默认主题应是多色彩")

    def test_custom_theme_overrides_default(self):
        """传入 theme 参数时应使用用户主题，而非默认。"""
        from xmind_tool.writer import write_xmind

        custom = {
            "map": {"id": "x", "properties": {"svg:fill": "#f0f0f0"}},
            "centralTopic": {"id": "y", "properties": {"fo:color": "#ff0000"}},
        }
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "custom.xmind"
            write_xmind(
                [{"title": "T", "topic": {"title": "R"}}],
                str(out),
                theme=custom,
            )
            theme = self._read_content(out)[0]["theme"]
            self.assertEqual(theme["map"]["properties"]["svg:fill"], "#f0f0f0")
            self.assertNotIn("color-list", theme["map"]["properties"])

    def test_theme_ids_are_unique_per_call(self):
        """每次写出，theme 内各子项的 id 应重新生成，避免跨文件 id 重复。

        同一进程多次调用 write_xmind，注入的 theme 不应共享同一组 id
        （XMind 对重复 id 可能异常）。
        """
        from xmind_tool.writer import write_xmind

        ids_a, ids_b = [], []
        with TemporaryDirectory() as tmp:
            for name in ("a.xmind", "b.xmind"):
                out = Path(tmp) / name
                write_xmind([{"title": "T", "topic": {"title": "R"}}], str(out))
                theme = self._read_content(out)[0]["theme"]
                ids = [theme[k].get("id") for k in ("map", "centralTopic", "mainTopic")]
                (ids_a if name == "a.xmind" else ids_b).extend(ids)
        # 两次写出的 theme id 不应全相同
        self.assertNotEqual(ids_a, ids_b, msg="两次写出 theme id 重复")

    def test_no_theme_when_explicit_none(self):
        """theme=None 时不应注入（显式关闭主题）。"""
        from xmind_tool.writer import write_xmind

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "bare.xmind"
            write_xmind(
                [{"title": "T", "topic": {"title": "R"}}],
                str(out),
                theme=None,
            )
            self.assertNotIn("theme", self._read_content(out)[0])


if __name__ == "__main__":
    unittest.main()
