"""样式/图标 pass-through 测试 — RED 阶段。"""
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


SAMPLE_STYLES = {
    "theme": {"id": "foo", "name": "Foo"},
    "styles": [
        {"id": "style-1", "type": "topic", "properties": {"fill": "#ff0000"}},
    ],
    "masterStyles": [],
}

SAMPLE_MANIFEST = {
    "fileFormat": ".xmind",
    "version": "1.0",
}


class TestStylesPassthrough(unittest.TestCase):

    def test_read_xmind_full_returns_styles_and_manifest(self):
        """read_xmind_full 应能返回 sheets + styles + manifest。"""
        from xmind_tool.reader import read_xmind_full

        with TemporaryDirectory() as tmp:
            xmind_path = Path(tmp) / "test.xmind"
            with zipfile.ZipFile(xmind_path, "w") as zf:
                zf.writestr("content.json", json.dumps([{
                    "id": "s1", "class": "sheet", "title": "T",
                    "rootTopic": {"id": "r1", "class": "topic", "title": "R"},
                }], ensure_ascii=False))
                zf.writestr("styles.json", json.dumps(SAMPLE_STYLES, ensure_ascii=False))
                zf.writestr("manifest.json", json.dumps(SAMPLE_MANIFEST, ensure_ascii=False))

            result = read_xmind_full(str(xmind_path))
            self.assertIn("sheets", result)
            self.assertIn("styles", result)
            self.assertIn("manifest", result)
            self.assertEqual(result["sheets"][0]["title"], "T")
            self.assertEqual(result["styles"]["theme"]["id"], "foo")
            self.assertEqual(result["manifest"]["version"], "1.0")

    def test_read_xmind_full_no_styles_returns_empty(self):
        """没有 styles.json 时应返回空 dict（不报错）。"""
        from xmind_tool.reader import read_xmind_full

        with TemporaryDirectory() as tmp:
            xmind_path = Path(tmp) / "no_styles.xmind"
            with zipfile.ZipFile(xmind_path, "w") as zf:
                zf.writestr("content.json", json.dumps([{
                    "id": "s1", "class": "sheet", "title": "T",
                    "rootTopic": {"id": "r1", "class": "topic", "title": "R"},
                }], ensure_ascii=False))
                zf.writestr("metadata.json", "{}")

            result = read_xmind_full(str(xmind_path))
            self.assertEqual(result["styles"], {})
            self.assertEqual(result["manifest"], {})

    def test_write_xmind_full_includes_styles(self):
        """write_xmind_full 注入 styles 后，zip 内应包含 styles.json。"""
        from xmind_tool.writer import write_xmind_full

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "styled.xmind"
            sheets = [{"title": "S", "topic": {"title": "R"}}]
            write_xmind_full(sheets, str(out), styles=SAMPLE_STYLES, manifest=SAMPLE_MANIFEST)

            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                self.assertIn("content.json", names)
                self.assertIn("metadata.json", names)
                self.assertIn("styles.json", names)
                self.assertIn("manifest.json", names)
                styles_back = json.loads(zf.read("styles.json"))
                self.assertEqual(styles_back["theme"]["id"], "foo")

    def test_write_xmind_full_no_styles_writes_compliant_metadata(self):
        """write_xmind_full 不传 styles 时：
        - 不写 styles.json
        - 仍写 content.json / metadata.json / manifest.json
        - metadata 含 dataStructureVersion / layoutEngineVersion（XMind 校验所需）
        - manifest 默认含 file-entries（XMind 校验所需）
        缺这些字段会导致 XMind 报 "not a valid XMind File"。
        """
        from xmind_tool.writer import write_xmind_full

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "plain.xmind"
            sheets = [{"title": "S", "topic": {"title": "R"}}]
            write_xmind_full(sheets, str(out))

            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                self.assertNotIn("styles.json", names)
                self.assertIn("content.json", names)
                self.assertIn("metadata.json", names)
                self.assertIn("manifest.json", names)
                meta = json.loads(zf.read("metadata.json"))
                self.assertIn("dataStructureVersion", meta)
                self.assertIn("layoutEngineVersion", meta)
                mani = json.loads(zf.read("manifest.json"))
                self.assertIn("file-entries", mani)

    def test_styles_roundtrip_preserves_bytes(self):
        """read_xmind_full → write_xmind_full 应能完整保留 styles.json。"""
        from xmind_tool.reader import read_xmind_full
        from xmind_tool.writer import write_xmind_full

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.xmind"
            with zipfile.ZipFile(src, "w") as zf:
                zf.writestr("content.json", json.dumps([{
                    "id": "s1", "class": "sheet", "title": "T",
                    "rootTopic": {"id": "r1", "class": "topic", "title": "R"},
                }], ensure_ascii=False))
                zf.writestr("styles.json", json.dumps(SAMPLE_STYLES, ensure_ascii=False))
                zf.writestr("manifest.json", json.dumps(SAMPLE_MANIFEST, ensure_ascii=False))

            data = read_xmind_full(str(src))
            dst = Path(tmp) / "dst.xmind"
            write_xmind_full(data["sheets"], str(dst), styles=data["styles"], manifest=data["manifest"])

            with zipfile.ZipFile(dst) as zf:
                styles_back = json.loads(zf.read("styles.json"))
                self.assertEqual(styles_back, SAMPLE_STYLES)
                manifest_back = json.loads(zf.read("manifest.json"))
                self.assertEqual(manifest_back, SAMPLE_MANIFEST)


if __name__ == "__main__":
    unittest.main()
