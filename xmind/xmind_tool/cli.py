"""
xmind_tool.cli: 命令行入口。

子命令：
- read    读 .xmind 输出为 json/yaml/md
- write   从 json/yaml 写入 .xmind
- convert 双向转换（按文件扩展名自动判断方向）
- info    显示文件摘要

不带任何参数时打印帮助。
"""
import argparse
import json
import sys
from pathlib import Path

from .reader import read_xmind
from .writer import write_xmind
from .convert import (
    xmind_to_json,
    xmind_to_yaml,
    xmind_to_markdown,
    xmind_to_csv,
    xmind_to_opml,
    json_to_xmind,
    yaml_to_xmind,
    markdown_to_xmind,
)

_XMIND_EXT = ".xmind"
_FROM_JSON_EXT = {".json"}
_FROM_YAML_EXT = {".yaml", ".yml"}
_FROM_MD_EXT = {".md", ".markdown"}


def _resolve_theme(args) -> object:
    """把 CLI 的 --theme/--no-theme 解析为 writer 期望的 theme 值。

    返回：
    - ``USE_DEFAULT_THEME`` sentinel：用内置默认主题（缺省）
    - ``dict``：自定义主题（从 --theme 文件加载）
    - ``None``：不注入主题（--no-theme）
    """
    from .writer import USE_DEFAULT_THEME
    if getattr(args, "no_theme", False):
        return None
    theme_path = getattr(args, "theme", None)
    if theme_path:
        import json
        return json.loads(Path(theme_path).read_text(encoding="utf-8"))
    return USE_DEFAULT_THEME


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xmind-tool",
        description="轻量级 .xmind 读写与格式转换工具",
    )
    sub = p.add_subparsers(dest="cmd")

    # read
    p_read = sub.add_parser("read", help="读 .xmind 并输出为指定格式")
    p_read.add_argument("input", help="输入 .xmind 文件路径")
    p_read.add_argument(
        "--format", "-f",
        choices=["json", "yaml", "md", "csv", "opml"],
        default="json",
        help="输出格式（默认 json）",
    )
    p_read.add_argument("--output", "-o", help="输出文件路径（缺省打印到 stdout）")
    p_read.add_argument(
        "--session",
        default=None,
        help="会话 id：解析时把结果缓存到 .xmind-cache/<session>/，供 memory 命令取回",
    )

    # memory
    p_mem = sub.add_parser("memory", help="取回之前 read --session 缓存的 markdown")
    p_mem.add_argument("input", help="输入 .xmind 文件路径")
    p_mem.add_argument("--session", required=True, help="会话 id")

    # write
    p_write = sub.add_parser("write", help="从 json/yaml/md 写入 .xmind")
    p_write.add_argument("input", help="输入 .json / .yaml / .md 文件")
    p_write.add_argument("--output", "-o", required=True, help="输出 .xmind 文件路径")
    p_write.add_argument(
        "--format", "-f",
        choices=["zen", "legacy"],
        default="zen",
        help="输出格式（默认 zen，legacy 为 XMind 8 兼容）",
    )
    p_write.add_argument("--theme", help="自定义主题 JSON 文件路径")
    p_write.add_argument(
        "--no-theme", action="store_true", help="不注入主题（朴素白底）"
    )

    # convert
    p_conv = sub.add_parser("convert", help="双向转换（按扩展名自动判断方向）")
    p_conv.add_argument("input", help="输入文件")
    p_conv.add_argument("--output", "-o", required=True, help="输出文件")
    p_conv.add_argument(
        "--format", "-f",
        choices=["zen", "legacy"],
        default="zen",
        help="写出 .xmind 时的格式（默认 zen，仅 other→xmind 方向生效）",
    )
    p_conv.add_argument("--theme", help="自定义主题 JSON 文件路径（仅 other→xmind 生效）")
    p_conv.add_argument(
        "--no-theme", action="store_true", help="不注入主题（朴素白底）"
    )

    # info
    p_info = sub.add_parser("info", help="显示 .xmind 文件摘要")
    p_info.add_argument("input", help="输入 .xmind 文件")

    return p


def _cmd_read(args) -> int:
    fmt = args.format
    if fmt == "json":
        data = read_xmind(args.input)
        text = json.dumps(data, ensure_ascii=False, indent=2)
    elif fmt == "yaml":
        data = read_xmind(args.input)
        import yaml
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    elif fmt == "md":
        # 复用 convert.xmind_to_markdown（含 ## 关联 注脚段），
        # 不再在此重复 _render_topic_md 逻辑，避免两条 md 渲染路径分叉。
        from .convert import xmind_to_markdown
        if args.output:
            xmind_to_markdown(args.input, args.output)
            return 0
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile("r", suffix=".md", delete=False, encoding="utf-8") as tmp:
            tmp_path = tmp.name
        xmind_to_markdown(args.input, tmp_path)
        with open(tmp_path, "r", encoding="utf-8") as f:
            text = f.read()
        Path(tmp_path).unlink()
    elif fmt == "csv":
        # CSV 必须写文件（多行），用 --output 或临时文件
        from .convert import xmind_to_csv
        from tempfile import NamedTemporaryFile
        if args.output:
            xmind_to_csv(args.input, args.output)
            return 0
        with NamedTemporaryFile("r", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp_path = tmp.name
        xmind_to_csv(args.input, tmp_path)
        with open(tmp_path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        Path(tmp_path).unlink()
    elif fmt == "opml":
        from .convert import xmind_to_opml
        from tempfile import NamedTemporaryFile
        if args.output:
            xmind_to_opml(args.input, args.output)
            return 0
        with NamedTemporaryFile("r", suffix=".opml", delete=False, encoding="utf-8") as tmp:
            tmp_path = tmp.name
        xmind_to_opml(args.input, tmp_path)
        with open(tmp_path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        Path(tmp_path).unlink()
    else:
        print(f"unsupported format: {fmt}", file=sys.stderr)
        return 2

    if args.output and fmt in ("json", "yaml", "md"):
        Path(args.output).write_text(text, encoding="utf-8")
    elif not args.output:
        print(text)

    # 会话记忆：解析后把结果缓存到磁盘，供 memory 命令断点取回。
    # 仅 md 等可稳定重读的文本格式缓存（csv/opml 走临时文件，无 text 变量语义）。
    if args.session and fmt in ("json", "yaml", "md"):
        from .memory import save
        try:
            save(args.input, args.session, text)
        except (ValueError, OSError) as e:
            print(f"警告: 缓存写入失败: {e}", file=sys.stderr)
    return 0


def _cmd_memory(args) -> int:
    """取回之前 read --session 缓存的 markdown。"""
    from .memory import load
    try:
        text = load(args.input, args.session)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2
    if text is None:
        print(f"无缓存: {args.input} (session={args.session})", file=sys.stderr)
        return 1
    print(text)
    return 0


def _cmd_write(args) -> int:
    fmt = args.format
    theme = _resolve_theme(args)
    src_ext = Path(args.input).suffix.lower()
    if src_ext in _FROM_JSON_EXT:
        json_to_xmind(args.input, args.output, fmt, theme)
    elif src_ext in _FROM_YAML_EXT:
        yaml_to_xmind(args.input, args.output, fmt, theme)
    elif src_ext in _FROM_MD_EXT:
        markdown_to_xmind(args.input, args.output, fmt, theme)
    else:
        print(f"不支持的输入格式: {src_ext}（仅支持 .json / .yaml / .yml / .md）", file=sys.stderr)
        return 2
    return 0


def _cmd_convert(args) -> int:
    src_ext = Path(args.input).suffix.lower()
    dst_ext = Path(args.output).suffix.lower()
    fmt = args.format
    theme = _resolve_theme(args)

    # xmind -> xmind 没必要
    if src_ext == _XMIND_EXT and dst_ext == _XMIND_EXT:
        print("源和目标都是 .xmind，无需转换", file=sys.stderr)
        return 2

    # xmind -> other
    if src_ext == _XMIND_EXT:
        if dst_ext == ".json":
            xmind_to_json(args.input, args.output)
        elif dst_ext in _FROM_YAML_EXT:
            xmind_to_yaml(args.input, args.output)
        elif dst_ext in _FROM_MD_EXT:
            xmind_to_markdown(args.input, args.output)
        elif dst_ext == ".csv":
            xmind_to_csv(args.input, args.output)
        elif dst_ext == ".opml":
            xmind_to_opml(args.input, args.output)
        else:
            print(f"不支持的输出格式: {dst_ext}", file=sys.stderr)
            return 2
        return 0

    # other -> xmind
    if dst_ext == _XMIND_EXT:
        if src_ext in _FROM_JSON_EXT:
            json_to_xmind(args.input, args.output, fmt, theme)
        elif src_ext in _FROM_YAML_EXT:
            yaml_to_xmind(args.input, args.output, fmt, theme)
        elif src_ext in _FROM_MD_EXT:
            markdown_to_xmind(args.input, args.output, fmt, theme)
        else:
            print(f"不支持的输入格式: {src_ext}", file=sys.stderr)
            return 2
        return 0

    print(f"无法识别转换方向: {src_ext} -> {dst_ext}", file=sys.stderr)
    return 2


def _count_topics(topic: dict) -> int:
    """递归统计 topic 数量（含自身）。"""
    return 1 + sum(_count_topics(c) for c in (topic.get("topics") or []))


def _cmd_info(args) -> int:
    data = read_xmind(args.input)
    print(f"文件: {args.input}")
    print(f"Sheet 数: {len(data)}")
    for i, sheet in enumerate(data):
        topic = sheet.get("topic", {})
        title = topic.get("title", "(no title)")
        n_topics = _count_topics(topic)
        structure = sheet.get("structure", "-")
        print(f"  [{i}] sheet: {sheet.get('title', '?')!r}  root: {title!r}  topics: {n_topics}  structure: {structure}")
        # 列出直接子节点
        for child in topic.get("topics", []) or []:
            print(f"      - {child.get('title', '?')!r}")
    return 0


def main(argv=None) -> int:
    # argv=None 表示从命令行直接调用（console_script / python -m），
    # 必须读 sys.argv；否则 console_script 不带参数调用时永远只打印 help。
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd is None:
        parser.print_help()
        return 0

    try:
        handler = {
            "read": _cmd_read,
            "write": _cmd_write,
            "convert": _cmd_convert,
            "info": _cmd_info,
            "memory": _cmd_memory,
        }[args.cmd]
        return handler(args)
    except FileNotFoundError as e:
        print(f"文件不存在: {e.filename}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
