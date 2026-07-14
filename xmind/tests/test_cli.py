"""CLI 模块测试 — RED 阶段。"""
import json
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

SAMPLES = Path(__file__).parent.parent / "samples"


def _run_cli(*args):
    """调用 CLI 并返回 (returncode, stdout, stderr)。"""
    from xmind_tool.cli import main
    import io
    from contextlib import redirect_stdout, redirect_stderr

    out_buf, err_buf = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = main(list(args))
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return code, out_buf.getvalue(), err_buf.getvalue()


class TestCLI(unittest.TestCase):

    # --- read ---

    def test_read_to_stdout_default_json(self):
        """read 不指定 --format 时默认输出 JSON 到 stdout。"""
        code, out, err = _run_cli("read", str(SAMPLES / "demo.xmind"))
        self.assertEqual(code, 0, msg=err)
        data = json.loads(out)
        self.assertEqual(data[0]["title"], "示例脑图")

    def test_read_with_format_yaml(self):
        """read --format yaml 应输出 YAML。"""
        code, out, err = _run_cli("read", str(SAMPLES / "demo.xmind"), "--format", "yaml")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("示例脑图", out)
        self.assertIn("中心主题", out)

    def test_read_with_format_markdown(self):
        """read --format md 应输出 markdown。"""
        code, out, err = _run_cli("read", str(SAMPLES / "demo.xmind"), "--format", "md")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("# 示例脑图", out)
        self.assertIn("## 中心主题", out)

    def test_read_csv_to_stdout_has_no_bom(self):
        """read --format csv 输出到 stdout 时不应含 BOM（文件才有 BOM，stdout 要干净）。"""
        code, out, err = _run_cli("read", str(SAMPLES / "demo.xmind"), "--format", "csv")
        self.assertEqual(code, 0, msg=err)
        self.assertFalse(out.startswith("\ufeff"), msg="stdout 输出了 BOM")
        self.assertTrue(out.startswith("sheet,"))

    def test_read_with_output_file(self):
        """read --output 应写到文件。"""
        with TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "out.json"
            code, _, err = _run_cli(
                "read", str(SAMPLES / "demo.xmind"),
                "--output", str(out_path),
            )
            self.assertEqual(code, 0, msg=err)
            self.assertTrue(out_path.exists())
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["title"], "示例脑图")

    def test_read_missing_file_returns_error(self):
        """读不存在的文件应返回非 0。"""
        code, _, err = _run_cli("read", "nonexistent.xmind")
        self.assertNotEqual(code, 0)

    # --- session memory ---

    def test_read_with_session_caches_md(self):
        """read --format md --session 应把解析结果缓存到 .xmind-cache/。"""
        import shutil
        from xmind_tool.memory import cache_path

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "map.xmind"
            shutil.copy(SAMPLES / "demo.xmind", src)  # 复制，保留原 fixture
            code, out, err = _run_cli(
                "read", str(src), "--format", "md", "--session", "sess-1"
            )
            self.assertEqual(code, 0, msg=err)
            cache = cache_path(src, "sess-1")
            self.assertTrue(cache.exists())
            self.assertIn("示例脑图", cache.read_text(encoding="utf-8"))

    def test_memory_command_returns_cached(self):
        """memory 命令应取回之前 read --session 缓存的 markdown。"""
        import shutil

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "map.xmind"
            shutil.copy(SAMPLES / "demo.xmind", src)
            _run_cli("read", str(src), "--format", "md", "--session", "sess-1")
            code, out, err = _run_cli("memory", str(src), "--session", "sess-1")
            self.assertEqual(code, 0, msg=err)
            self.assertIn("示例脑图", out)

    def test_memory_command_no_cache_errors(self):
        """memory 命令在无缓存时应返回非 0 并提示。"""
        import shutil

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "uncached.xmind"
            shutil.copy(SAMPLES / "demo.xmind", src)
            code, _, err = _run_cli("memory", str(src), "--session", "sess-x")
            self.assertNotEqual(code, 0)
            self.assertIn("无缓存", err)

    # --- write ---

    def test_write_from_json(self):
        """write 接受 .json 输入，输出 .xmind。"""
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            dst = Path(tmp) / "out.xmind"
            src.write_text(
                json.dumps([{
                    "title": "CLI Test",
                    "topic": {"title": "R", "topics": [{"title": "C"}]},
                }], ensure_ascii=False),
                encoding="utf-8",
            )
            code, _, err = _run_cli("write", str(src), "--output", str(dst))
            self.assertEqual(code, 0, msg=err)
            self.assertTrue(dst.exists())

    def test_write_from_yaml(self):
        """write 接受 .yaml 输入，输出 .xmind。"""
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.yaml"
            dst = Path(tmp) / "out.xmind"
            src.write_text(
                "- title: CLI YAML\n  topic:\n    title: R\n",
                encoding="utf-8",
            )
            code, _, err = _run_cli("write", str(src), "--output", str(dst))
            self.assertEqual(code, 0, msg=err)
            self.assertTrue(dst.exists())

    def test_write_legacy_format(self):
        """write --format legacy 应输出 content.xml 而非 content.json。"""
        import zipfile

        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            dst = Path(tmp) / "out.xmind"
            src.write_text(
                json.dumps([{
                    "title": "Legacy CLI",
                    "topic": {"title": "R", "topics": [{"title": "C"}]},
                }], ensure_ascii=False),
                encoding="utf-8",
            )
            code, _, err = _run_cli(
                "write", str(src), "--output", str(dst), "--format", "legacy"
            )
            self.assertEqual(code, 0, msg=err)
            with zipfile.ZipFile(dst) as zf:
                names = set(zf.namelist())
            self.assertIn("content.xml", names)
            self.assertNotIn("content.json", names)

    def test_write_default_injects_theme(self):
        """write 默认应注入主题（生成的图打开美观）。"""
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            dst = Path(tmp) / "out.xmind"
            src.write_text(
                json.dumps([{"title": "T", "topic": {"title": "R"}}], ensure_ascii=False),
                encoding="utf-8",
            )
            code, _, err = _run_cli("write", str(src), "--output", str(dst))
            self.assertEqual(code, 0, msg=err)
            with zipfile.ZipFile(dst) as zf:
                content = json.loads(zf.read("content.json"))
            self.assertIn("theme", content[0])
            self.assertIn("color-list", content[0]["theme"]["map"]["properties"])

    def test_write_no_theme_flag(self):
        """write --no-theme 应不注入主题。"""
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            dst = Path(tmp) / "out.xmind"
            src.write_text(
                json.dumps([{"title": "T", "topic": {"title": "R"}}], ensure_ascii=False),
                encoding="utf-8",
            )
            code, _, err = _run_cli(
                "write", str(src), "--output", str(dst), "--no-theme"
            )
            self.assertEqual(code, 0, msg=err)
            with zipfile.ZipFile(dst) as zf:
                content = json.loads(zf.read("content.json"))
            self.assertNotIn("theme", content[0])

    def test_write_theme_from_file(self):
        """write --theme <file.json> 应加载自定义主题。"""
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            dst = Path(tmp) / "out.xmind"
            theme_file = Path(tmp) / "mytheme.json"
            src.write_text(
                json.dumps([{"title": "T", "topic": {"title": "R"}}], ensure_ascii=False),
                encoding="utf-8",
            )
            custom_theme = {
                "map": {"id": "x", "properties": {"svg:fill": "#abcdef"}},
                "centralTopic": {"id": "y", "properties": {}},
            }
            theme_file.write_text(json.dumps(custom_theme, ensure_ascii=False), encoding="utf-8")
            code, _, err = _run_cli(
                "write", str(src), "--output", str(dst), "--theme", str(theme_file)
            )
            self.assertEqual(code, 0, msg=err)
            with zipfile.ZipFile(dst) as zf:
                content = json.loads(zf.read("content.json"))
            self.assertEqual(
                content[0]["theme"]["map"]["properties"]["svg:fill"], "#abcdef"
            )

    # --- convert ---

    def test_convert_xmind_to_json(self):
        """convert 应能根据输出扩展名推断目标格式。"""
        with TemporaryDirectory() as tmp:
            src = SAMPLES / "demo.xmind"
            dst = Path(tmp) / "out.json"
            code, _, err = _run_cli("convert", str(src), "--output", str(dst))
            self.assertEqual(code, 0, msg=err)
            self.assertTrue(dst.exists())
            data = json.loads(dst.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["title"], "示例脑图")

    def test_convert_json_to_xmind(self):
        """convert 应能反向：从 json 生成 xmind。"""
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            dst = Path(tmp) / "out.xmind"
            src.write_text(
                json.dumps([{"title": "X", "topic": {"title": "R"}}], ensure_ascii=False),
                encoding="utf-8",
            )
            code, _, err = _run_cli("convert", str(src), "--output", str(dst))
            self.assertEqual(code, 0, msg=err)
            self.assertTrue(dst.exists())

    # --- info ---

    def test_info_shows_summary(self):
        """info 应展示文件摘要（sheet 数、根标题、子节点数）。"""
        code, out, err = _run_cli("info", str(SAMPLES / "demo.xmind"))
        self.assertEqual(code, 0, msg=err)
        self.assertIn("示例脑图", out)
        self.assertIn("中心主题", out)
        # 应包含子节点信息
        self.assertIn("分支 1", out)

    def test_no_args_shows_help(self):
        """不带参数时显示帮助（不报错）。"""
        code, out, _ = _run_cli()
        self.assertEqual(code, 0)
        # 帮助里应包含子命令名
        for cmd in ("read", "write", "convert", "info"):
            self.assertIn(cmd, out)


class TestCliDispatchFromSysArgv(unittest.TestCase):
    """回归：console_script 入口点（main() 不传 argv）必须读 sys.argv 分发子命令。

    历史 bug：main(argv=None) 里 ``if not argv: print_help; return``，
    导致 console_script 调用 ``main()`` 时 argv=None 为 falsy，永远只打印
    帮助退出，子命令根本不执行。test_cli 的其它测试都显式传 list(args)，
    绕过了 argv=None 分支，所以全绿但 console_script 实际不可用。
    这里通过 monkeypatch sys.argv 模拟真实 console_script 调用。
    """

    def test_main_no_argv_reads_sys_argv_dispatches_subcommand(self):
        """main() 不带 argv 参数时，应从 sys.argv 读取并分发到 info。"""
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from xmind_tool.cli import main

        argv_saved = sys.argv
        sys.argv = ["xmind-tool", "info", str(SAMPLES / "demo.xmind")]
        out_buf, err_buf = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = main()  # 不传 argv —— 模拟 console_script
        finally:
            sys.argv = argv_saved
        self.assertEqual(code, 0, msg=err_buf.getvalue())
        # info 应真正执行而非打印 help：输出里要有文件摘要内容
        out = out_buf.getvalue()
        self.assertIn("示例脑图", out, msg="info 子命令未执行，疑似又退化为打印 help")
        self.assertIn("Sheet 数", out)

    def test_main_no_argv_dispatches_read_md(self):
        """main() 不带 argv 时应能分发到 read --format md。"""
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from xmind_tool.cli import main

        argv_saved = sys.argv
        sys.argv = ["xmind-tool", "read", str(SAMPLES / "demo.xmind"), "--format", "md"]
        out_buf, err_buf = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                code = main()
        finally:
            sys.argv = argv_saved
        self.assertEqual(code, 0, msg=err_buf.getvalue())
        out = out_buf.getvalue()
        self.assertIn("# 示例脑图", out, msg="read md 子命令未执行")


if __name__ == "__main__":
    unittest.main()
