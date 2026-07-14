"""xmind → CSV / OPML 转换测试 — RED 阶段。"""
import csv
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

SAMPLES = Path(__file__).parent.parent / "samples"


class TestXmindToCSV(unittest.TestCase):
    """xmind_to_csv: 拍平为行，保留 sheet/depth/path/title/note/labels/makers/link"""

    def test_csv_has_header(self):
        """CSV 第一行应为 header。"""
        from xmind_tool.convert import xmind_to_csv
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.csv"
            xmind_to_csv(str(SAMPLES / "demo.xmind"), str(out))
            with open(out, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                header = next(reader)
                self.assertEqual(
                    header,
                    ["sheet", "depth", "path", "title", "note", "labels", "makers", "link"],
                )

    def test_csv_root_topic_row(self):
        """根 topic 应作为第 0 行的 row，path = title。"""
        from xmind_tool.convert import xmind_to_csv
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.csv"
            xmind_to_csv(str(SAMPLES / "demo.xmind"), str(out))
            with open(out, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            # 第一行应是根 topic
            row0 = rows[0]
            self.assertEqual(row0["sheet"], "示例脑图")
            self.assertEqual(row0["depth"], "0")
            self.assertEqual(row0["path"], "中心主题")
            self.assertEqual(row0["title"], "中心主题")

    def test_csv_nested_topics_have_breadcrumb_path(self):
        """嵌套子 topic 的 path 形如 'A > B > C'。"""
        from xmind_tool.convert import xmind_to_csv
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.csv"
            xmind_to_csv(str(SAMPLES / "demo.xmind"), str(out))
            with open(out, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            # 找 '子节点 1.1' — path 应为 '中心主题 > 分支 1 > 子节点 1.1'
            leaf = next(r for r in rows if r["title"] == "子节点 1.1")
            self.assertEqual(leaf["depth"], "2")
            self.assertEqual(leaf["path"], "中心主题 > 分支 1 > 子节点 1.1")
            # labels/makers
            self.assertEqual(leaf["labels"], "重要")
            self.assertEqual(leaf["makers"], "priority-1")

    def test_csv_meta_fields_joined_with_comma(self):
        """多个 labels / makers 用 ',' 连接。"""
        from xmind_tool.convert import xmind_to_csv
        # 构造一个 sheets 数据并写到临时文件
        with TemporaryDirectory() as tmp:
            from xmind_tool.writer import write_xmind
            sheets = [{
                "title": "T",
                "topic": {
                    "title": "Root",
                    "topics": [{
                        "title": "Child",
                        "labels": ["a", "b", "c"],
                        "makers": ["task", "flag"],
                        "link": "https://x.com",
                    }],
                },
            }]
            xmind_path = Path(tmp) / "in.xmind"
            write_xmind(sheets, str(xmind_path))
            csv_out = Path(tmp) / "out.csv"
            xmind_to_csv(str(xmind_path), str(csv_out))
            with open(csv_out, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            child = next(r for r in rows if r["title"] == "Child")
            self.assertEqual(child["labels"], "a, b, c")
            self.assertEqual(child["makers"], "task, flag")
            self.assertEqual(child["link"], "https://x.com")

    def test_csv_has_utf8_bom(self):
        """CSV 应以 UTF-8 BOM 开头，否则 Windows Excel 用 GBK 解码中文会乱码。

        Excel 识别无 BOM 的 UTF-8 CSV 时默认按系统 ANSI(GBK) 解码，
        中文显示为乱码。写入 utf-8-sig 让 Excel 自动识别为 UTF-8。
        """
        from xmind_tool.convert import xmind_to_csv
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.csv"
            xmind_to_csv(str(SAMPLES / "demo.xmind"), str(out))
            head = out.read_bytes()[:3]
            self.assertEqual(
                head, b"\xef\xbb\xbf",
                msg="CSV 缺少 UTF-8 BOM，Excel 打开会乱码",
            )

    def test_csv_multiple_sheets(self):
        """多 sheet 时每行带 sheet 列。"""
        from xmind_tool.convert import xmind_to_csv
        from xmind_tool.writer import write_xmind
        with TemporaryDirectory() as tmp:
            xmind_path = Path(tmp) / "in.xmind"
            write_xmind([
                {"title": "A", "topic": {"title": "RA"}},
                {"title": "B", "topic": {"title": "RB"}},
            ], str(xmind_path))
            csv_out = Path(tmp) / "out.csv"
            xmind_to_csv(str(xmind_path), str(csv_out))
            with open(csv_out, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            sheets = sorted({r["sheet"] for r in rows})
            self.assertEqual(sheets, ["A", "B"])


class TestXmindToOPML(unittest.TestCase):
    """xmind_to_opml: 保留树形 + 自定义属性"""

    def test_opml_is_valid_xml(self):
        """输出应是合法 XML 2.0 opml 文档。"""
        from xmind_tool.convert import xmind_to_opml
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.opml"
            xmind_to_opml(str(SAMPLES / "demo.xmind"), str(out))
            tree = ET.parse(out)
            root = tree.getroot()
            self.assertEqual(root.tag, "opml")
            self.assertEqual(root.attrib.get("version"), "2.0")

    def test_opml_preserves_hierarchy(self):
        """OPML outline 嵌套深度应与 xmind topic 嵌套一致。"""
        from xmind_tool.convert import xmind_to_opml
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.opml"
            xmind_to_opml(str(SAMPLES / "demo.xmind"), str(out))
            tree = ET.parse(out)
            body = tree.getroot().find("body")
            # demo.xmind 有 1 sheet -> 1 个顶层 outline（sheet），其下 root outline
            top_outlines = body.findall("outline")
            self.assertEqual(len(top_outlines), 1)
            sheet_outline = top_outlines[0]
            self.assertEqual(sheet_outline.attrib["text"], "示例脑图")
            # sheet_outline 下面有 root outline（中心主题），其下 3 个 branches
            root_outlines = sheet_outline.findall("outline")
            self.assertEqual(len(root_outlines), 1)
            root = root_outlines[0]
            self.assertEqual(root.attrib["text"], "中心主题")
            self.assertEqual(len(root.findall("outline")), 3)

    def test_opml_includes_meta_attributes(self):
        """note / labels / makers / link 应作为自定义属性（_note / _labels / _makers / _link）。"""
        from xmind_tool.convert import xmind_to_opml
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.opml"
            xmind_to_opml(str(SAMPLES / "demo.xmind"), str(out))
            tree = ET.parse(out)
            # 找到 "子节点 1.1" outline
            for o in tree.iter("outline"):
                if o.attrib.get("text") == "子节点 1.1":
                    self.assertEqual(o.attrib.get("_labels"), "重要")
                    self.assertEqual(o.attrib.get("_makers"), "priority-1")
                    break
            else:
                self.fail("未找到 '子节点 1.1' outline")

    def test_opml_includes_note_attribute(self):
        """note 应作为 _note 属性。"""
        from xmind_tool.convert import xmind_to_opml
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.opml"
            xmind_to_opml(str(SAMPLES / "demo.xmind"), str(out))
            tree = ET.parse(out)
            for o in tree.iter("outline"):
                if o.attrib.get("text") == "分支 1":
                    self.assertIn("_note", o.attrib)
                    self.assertIn("分支1的备注", o.attrib["_note"])
                    break
            else:
                self.fail("未找到 '分支 1' outline")


class TestDispatchers(unittest.TestCase):
    """xmind_to / CLI dispatcher 应识别 csv 和 opml"""

    def test_xmind_to_csv_dispatch(self):
        from xmind_tool.convert import xmind_to
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.csv"
            xmind_to(str(SAMPLES / "demo.xmind"), str(out), fmt="csv")
            self.assertTrue(out.exists())
            self.assertTrue(out.read_text(encoding="utf-8-sig").startswith("sheet,"))

    def test_xmind_to_opml_dispatch(self):
        from xmind_tool.convert import xmind_to
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.opml"
            xmind_to(str(SAMPLES / "demo.xmind"), str(out), fmt="opml")
            self.assertTrue(out.exists())
            self.assertTrue(out.read_text(encoding="utf-8").startswith("<?xml"))


if __name__ == "__main__":
    unittest.main()
