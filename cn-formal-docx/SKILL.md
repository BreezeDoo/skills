---
name: cn-formal-docx
description: 中文规范文档(docx)的排版与格式规范。规定办法、规定、规程、大纲这类中文正式文档的字体、字号、行距、标题、图、题注、页码等排版规则,以及用 python-docx 实现的写法。Use when 生成或排版中文 Word 规范文档/正式文档/办法文件,当用户要求仿宋三号、标题分级导航、自动编号题注、图随章节、横版图分节符等中文公文排版时。自包含:内置 validate.py(ISO-IEC29500 Transitional schema)做 OOXML 校验,不依赖外部 docx skill。
---

# 中文规范文档排版 (cn-formal-docx)

## 定位与边界

本 skill 规定**中文规范文档的排版标准**——办法/规定/规程/大纲这类文档该长什么样。**只管排版格式,不管内容**(内容由写作者决定)。

本 skill **自包含**,不依赖外部 `docx` skill:用 python-docx 生成文档,复杂域(SEQ/REF/PAGE)生成期用 lxml 直构造;OOXML 校验用内置 `scripts/validate/validate.py`(ISO-IEC29500-4_2016 Transitional schema)+ vendored validators/schemas。**只管排版格式,不管内容**(内容由写作者决定)。

## 排版规范概要

- **字体(中英分体)**:中文仿宋_GB2312、英文 Times New Roman,用 font 对象 `{ascii, hAnsi, eastAsia}` 分体,不能只设字符串。
- **字号**:正文三号(32半点)、大标题18pt(36)、章标题三号加粗、题注与表格小四(24)、页脚小五(21)。
- **行距**:1.5 倍 `line:360, lineRule:"auto"`(必须显式 auto)。
- **标题**:章标题用 Heading 1 样式 + outlineLvl:0(否则导航窗格空)。大标题居中加粗普通段落,不进 Heading。
- **图**:随章节插(不堆附录);**大图**(宽幅架构图,宽高比>1.3)走横排分节符(竖→横→竖),**小图**(方图/竖图/图标)正文内联居中不切横排;同章多横排图合并一个横排 section,图间 pageBreakBefore;图按高度反算宽(横排高限520px、内联高限480px)保证图+题注同页。配置 `layout: "landscape"|"inline"|"auto"`。
- **题注**:SEQ 自动编号域 + 黑体小四 + 居中,域带 w:dirty。正文引用用 REF 交叉引用域指向题注书签 _Ref_figN,增删图 F9 自动同步。
- **其他**:首页空白、页脚页码(无页眉)、表格表头底色 E8EEF5、正文首行缩进640。

完整规范表、代码示例、GB/T 9704 速查、常见错误清单(30条)、**本对话修正史实操问题表(21条)**见 [REFERENCE.md](REFERENCE.md)。

## 题注域:生成期 lxml 直构造(无占位/正则)

复杂域(SEQ 题注、REF 交叉引用、PAGE 页码)在**生成时**用 lxml element 直接构造 fldChar begin/instrText/separate/缓存值run/end 三段式:缓存值 run 带正确 rPr(题注黑体小四、正文仿宋三号),SEQ 域缓存值外包书签 `_Ref_figN`,REF 域指向该书签。**不经过"空 SimpleField 占位 + 后处理正则替换"两段式**——那条路有两个脆弱点(SimpleField 缓存值无 rPr、REF 正则跨行贪婪吞 SEQ 域),均已从源头避开。

- 所有域的 fldChar begin 带 `w:dirty="true"`:Word 打开主动提示更新域,降低忘按 F9 的误操作(借鉴 zouchenzhen/docx-template-translator-skill 的 inject_toc_field.py)。
- 实现见 `scripts/gen_docx.py` 的 `add_field()`。

## 生成工作流(单脚本,无后处理)

1. 复制 `scripts/gen_docx.py` 改顶部 CONFIG(章节 md、图目录、FIG_BY_CHAPTER、REF_BY_CHAPTER、OUT)。
2. `python scripts/gen_docx.py [输出名.docx]`。
3. `python scripts/validate/validate.py 输出.docx`(validate.py + validators + schemas 已 vendor 进本 skill,零外部 skill 依赖)。

依赖:`pip install python-docx pillow lxml`(复杂域用 lxml;校验用本 skill 内置 validate.py,同样依赖 lxml,无新增依赖)。**禁用通用 docx unpack/pack 工具**:它们合并 run 会破坏复杂域(SEQ 丢失、段落减半),本脚本用 python-docx 直写 + zipfile 保存,不经 unpack/pack。

## 排版检查清单

生成后逐项核对(见 [REFERENCE.md](REFERENCE.md) 末尾清单):中英分体、三号1.5倍、Heading1+outlineLevel、图随章节、横排分节符、图高反算、SEQ+REF域+w:dirty+书签、首页空白、页脚页码、表头底色、w:jc表格对齐、validate通过(Transitional schema)。
