"""Markdown → xmind 反向转换测试 — RED 阶段。"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestMarkdownToXmind(unittest.TestCase):

    def test_basic_h1_h2_h3(self):
        """基础 H1 + H2 + H3 → 1 sheet / 1 root / 2 children。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# Project Plan
## Root
### Phase 1
### Phase 2
"""
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.md"
            dst = Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))

            sheets = read_xmind(str(dst))
            self.assertEqual(len(sheets), 1)
            self.assertEqual(sheets[0]["title"], "Project Plan")
            root = sheets[0]["topic"]
            self.assertEqual(root["title"], "Root")
            self.assertEqual(
                [t["title"] for t in root["topics"]],
                ["Phase 1", "Phase 2"],
            )

    def test_nested_h4(self):
        """H4 应作为 H3 的子节点。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# Sheet
## Root
### Child
#### GrandChild
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            root = read_xmind(str(dst))[0]["topic"]
            self.assertEqual(root["title"], "Root")
            child = root["topics"][0]
            self.assertEqual(child["title"], "Child")
            self.assertEqual(child["topics"][0]["title"], "GrandChild")

    def test_multiple_h1_creates_multiple_sheets(self):
        """多个 H1 → 多个 sheet。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# Sheet A
## Root A
# Sheet B
## Root B
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            sheets = read_xmind(str(dst))
            self.assertEqual(len(sheets), 2)
            self.assertEqual(sheets[0]["title"], "Sheet A")
            self.assertEqual(sheets[1]["title"], "Sheet B")
            self.assertEqual(sheets[0]["topic"]["title"], "Root A")
            self.assertEqual(sheets[1]["topic"]["title"], "Root B")

    def test_no_h1_uses_default_sheet_name(self):
        """缺 H1 时用默认名 'Imported' 创建单 sheet。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """## Just a root
### Child
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            sheets = read_xmind(str(dst))
            self.assertEqual(len(sheets), 1)
            self.assertEqual(sheets[0]["title"], "Imported")
            self.assertEqual(sheets[0]["topic"]["title"], "Just a root")

    def test_note_blockquote_attached_to_current_topic(self):
        """`> 文本` 应附加到最近的 topic 作为 note。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# S
## R
### Child
> A note here
> with continuation
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            child = read_xmind(str(dst))[0]["topic"]["topics"][0]
            self.assertEqual(child["note"], "A note here\nwith continuation")

    def test_labels_makers_link_lines(self):
        """**Labels:** / **Makers:** / [Link](url) 应被识别。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# S
## R
### Child
**Labels:** a, b, c
**Makers:** task, flag
[Click](https://example.com)
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            child = read_xmind(str(dst))[0]["topic"]["topics"][0]
            self.assertEqual(child["labels"], ["a", "b", "c"])
            self.assertEqual(child["makers"], ["task", "flag"])
            self.assertEqual(child["link"], "https://example.com")

    def test_second_h2_under_same_h1_starts_new_sheet(self):
        """同一 H1 下出现第二个 H2 时应开新 sheet（H2 自作 title + root）。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# Roadmap
## Q1
### Launch
## Q2
### Expand
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            sheets = read_xmind(str(dst))
            self.assertEqual(len(sheets), 2)
            # sheet 1: title=Roadmap, root=Q1
            self.assertEqual(sheets[0]["title"], "Roadmap")
            self.assertEqual(sheets[0]["topic"]["title"], "Q1")
            self.assertEqual(sheets[0]["topic"]["topics"][0]["title"], "Launch")
            # sheet 2: title=Q2 (self-referential root)
            self.assertEqual(sheets[1]["title"], "Q2")
            self.assertEqual(sheets[1]["topic"]["title"], "Q2")
            self.assertEqual(sheets[1]["topic"]["topics"][0]["title"], "Expand")

    def test_code_block_not_parsed(self):
        """代码块内的 `#` 标题、`> ` 等不应被解析。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# Real
## Root
```
# not a heading
> not a note
**Labels:** not, real
```
### Real child
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            sheets = read_xmind(str(dst))
            # 应该只有 1 sheet, 1 root, 1 child — 代码块内容被忽略
            self.assertEqual(len(sheets), 1)
            self.assertEqual(len(sheets[0]["topic"]["topics"]), 1)
            child = sheets[0]["topic"]["topics"][0]
            self.assertEqual(child["title"], "Real child")
            self.assertNotIn("note", child)
            self.assertNotIn("labels", child)


class TestDetachedAndSummaryReverse(unittest.TestCase):
    """[游离]/[概要] 标记的 md→xmind 反向解析，含 note 归属。"""

    def test_detached_note_attaches_to_detached_not_parent(self):
        """游离主题的 note 应挂在游离主题自己上，而非父节点。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# 压测
## 根
### 分支A
### [游离] 游离想法

> 这是游离主题的备注
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            root = read_xmind(str(dst))[0]["topic"]

            # 父节点（根）不应吃到游离主题的 note
            self.assertNotIn("note", root, msg="游离主题的 note 被错误挂到了父节点")

            # 游离主题自己应带 note
            detached = root.get("detached", [])
            self.assertEqual(len(detached), 1)
            self.assertEqual(detached[0]["title"], "游离想法")
            self.assertEqual(detached[0]["note"], "这是游离主题的备注")

    def test_summary_note_attaches_to_summary(self):
        """概要框的 note 应挂在概要自己上，而非父节点。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# 压测
## 根
### 分支A
### 分支B
### [概要] A和B的概要

> 概要框备注
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            root = read_xmind(str(dst))[0]["topic"]

            self.assertNotIn("note", root, msg="概要框的 note 被错误挂到了父节点")
            summary = root.get("summary", [])
            self.assertEqual(len(summary), 1)
            self.assertEqual(summary[0]["title"], "A和B的概要")
            self.assertEqual(summary[0]["note"], "概要框备注")


class TestMdInlineMarkupStripped(unittest.TestCase):
    """标题里的内联标记（**bold** / `code` / *italic*）应被剥离为纯文本。

    理由：XMind 的加粗语义在 style.properties.fo:font-weight，不在 title 文本里。
    md 的内联标记和 XMind 的富文本模型不兼容，强行保留星号/反引号会让 XMind
    显示出带符号的字面文本。本组测试要求 parser 把内联标记剥离成纯文本标题。
    """

    def test_bold_markers_stripped_from_title(self):
        """## **加粗** → title 为「加粗」，不带星号。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = "# Sheet\n## **加粗标题**\n### Child\n"
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            root = read_xmind(str(dst))[0]["topic"]
            self.assertEqual(root["title"], "加粗标题")

    def test_inline_code_stripped_from_title(self):
        """## Root `code` text → title 为「Root code text」，不带反引号。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = "# Sheet\n## Root `code` text\n"
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            root = read_xmind(str(dst))[0]["topic"]
            self.assertEqual(root["title"], "Root code text")

    def test_italic_markers_stripped_from_title(self):
        """### *斜体* 文字 → title 为「斜体 文字」，不带星号。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = "# Sheet\n## Root\n### *斜体* 文字\n"
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            child = read_xmind(str(dst))[0]["topic"]["topics"][0]
            self.assertEqual(child["title"], "斜体 文字")


class TestMdBulletListBecomesChildren(unittest.TestCase):
    """无序列表 `- item` 应成为 attached 子节点，而非被静默丢弃。

    现状（bug）：parser 只认 # 标题，`- bullet` 行被完全跳过，导致数据丢失且无报错。
    期望：把列表项当作当前栈顶 topic 的 attached 子节点。
    """

    def test_bullet_items_become_children(self):
        """`- one` / `- two` → 当前 topic 的两个 attached 子节点。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# Sheet
## Root
- bullet one
- bullet two
### heading child
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            root = read_xmind(str(dst))[0]["topic"]
            titles = [t["title"] for t in root["topics"]]
            self.assertIn("bullet one", titles)
            self.assertIn("bullet two", titles)
            self.assertIn("heading child", titles)

    def test_nested_bullet_under_bullet(self):
        """缩进列表项应嵌套为上一项的子节点。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# Sheet
## Root
- top
    - sub a
    - sub b
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            root = read_xmind(str(dst))[0]["topic"]
            top = root["topics"][0]
            self.assertEqual(top["title"], "top")
            subs = [t["title"] for t in top["topics"]]
            self.assertEqual(subs, ["sub a", "sub b"])


class TestMdCalloutRoundTrip(unittest.TestCase):
    """callout 的 md→xmind 反向识别（当前只有 xmind→md 单向，往返断在这里）。

    md 约定：`**Callout:** 文本` 行 → 当前 topic 的 callout 列表。
    """

    def test_callout_line_becomes_callout(self):
        """`**Callout:** hello` → topic.callout = ['hello']。"""
        from xmind_tool.convert import markdown_to_xmind
        from xmind_tool.reader import read_xmind

        md = """# Sheet
## Root
### Child
**Callout:** hello callout
"""
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.md", Path(tmp) / "out.xmind"
            src.write_text(md, encoding="utf-8")
            markdown_to_xmind(str(src), str(dst))
            child = read_xmind(str(dst))[0]["topic"]["topics"][0]
            self.assertEqual(child.get("callout"), ["hello callout"])


if __name__ == "__main__":
    unittest.main()
