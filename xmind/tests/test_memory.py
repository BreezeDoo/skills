"""Session memory 测试 — RED 阶段。

记忆文件应放在 .xmind 源文件所在目录的 .xmind-cache/<session>/ 下，
源目录不可写时回退到 cwd/.xmind-cache/<session>/。
"""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestCachePath(unittest.TestCase):
    def test_prefers_source_dir(self):
        """缓存路径首选源文件所在目录的 .xmind-cache/。"""
        from xmind_tool.memory import cache_path

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "map.xmind"
            src.touch()
            p = cache_path(src, "sess-1")
            # tmp/.xmind-cache/sess-1/map.md  -> parent.parent.parent == tmp
            self.assertEqual(p.parent.parent.parent, Path(tmp).resolve())
            self.assertEqual(p.parent.parent.name, ".xmind-cache")
            self.assertTrue(p.name.startswith("map"))

    def test_falls_back_to_cwd_when_source_unwritable(self):
        """源目录不可写时，回退到 cwd/.xmind-cache/。"""
        from xmind_tool.memory import cache_path

        with TemporaryDirectory() as src_dir:
            src = Path(src_dir) / "map.xmind"
            src.touch()
            # 制造不可写：去掉目录写权限（Windows 上 chmod 可能无效，跳过）
            if os.name == "nt":
                self.skipTest("chmod 对 Windows 不生效，不可写回退靠 save 实测")
            Path(src_dir).chmod(0o555)
            try:
                p = cache_path(src, "sess-1")
                cwd_cache = Path.cwd() / ".xmind-cache"
                self.assertTrue(str(p).startswith(str(cwd_cache)))
            finally:
                Path(src_dir).chmod(0o755)


class TestSaveLoad(unittest.TestCase):
    def test_save_then_load_roundtrip(self):
        """save 后 load 应取回相同内容。"""
        from xmind_tool.memory import save, load

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "map.xmind"
            src.touch()
            text = "# Sheet\n\n## 根\n- 子节点\n"
            save(src, "sess-1", text)
            self.assertEqual(load(src, "sess-1"), text)

    def test_load_returns_none_when_absent(self):
        """无缓存时 load 返回 None。"""
        from xmind_tool.memory import load

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "never_cached.xmind"
            src.touch()
            self.assertIsNone(load(src, "sess-1"))

    def test_sessions_are_isolated(self):
        """不同 session 的缓存互不干扰。"""
        from xmind_tool.memory import save, load

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "map.xmind"
            src.touch()
            save(src, "sess-A", "内容A")
            save(src, "sess-B", "内容B")
            self.assertEqual(load(src, "sess-A"), "内容A")
            self.assertEqual(load(src, "sess-B"), "内容B")

    def test_save_returns_path(self):
        """save 应返回实际写入的路径（含回退后的真实位置）。"""
        from xmind_tool.memory import save

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "map.xmind"
            src.touch()
            p = save(src, "sess-1", "x")
            self.assertTrue(Path(p).exists())


class TestSessionValidation(unittest.TestCase):
    def test_rejects_empty(self):
        """空 session id 应被拒。"""
        from xmind_tool.memory import validate_session_id
        with self.assertRaises(ValueError):
            validate_session_id("")

    def test_rejects_path_traversal(self):
        """含路径分隔符的 session id 应被拒（防穿越）。"""
        from xmind_tool.memory import validate_session_id
        for bad in ["a/b", "..", "../etc", "a\\b", "a/../b", "a:b"]:
            with self.assertRaises(ValueError, msg=f"应拒绝: {bad!r}"):
                validate_session_id(bad)

    def test_accepts_normal_id(self):
        """正常 id（字母数字-下划线-点）应通过并原样返回。"""
        from xmind_tool.memory import validate_session_id
        for ok in ["sess-1", "f47ac10b-58cc-4372", "abc_2026", "a.b.c"]:
            self.assertEqual(validate_session_id(ok), ok)


if __name__ == "__main__":
    unittest.main()
