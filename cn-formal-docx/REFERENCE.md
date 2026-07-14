# cn-formal-docx 排版参考与排坑

本文件是 SKILL.md 的补充:完整代码示例与排坑记录。日常触发看 SKILL.md 即可,需要写法细节或排错时查本文件。

## 完整排版规范表

| 元素 | 规范 | python-docx 写法 |
|---|---|---|
| 正文中文字体 | 仿宋_GB2312 | `rFonts w:eastAsia="仿宋_GB2312"`(见 apply_font) |
| 正文英文字体 | Times New Roman | `rFonts w:ascii/hAnsi="Times New Roman"` |
| 正文字号 | 三号 16pt | `run.font.size = Pt(16)` |
| 行距 | 1.5 倍 | `pf.line_spacing = 1.5`(转 spacing line=360 lineRule=auto) |
| 首行缩进 | 2 字符 | `pf.first_line_indent = Pt(32)`(三号2字符=640twips) |
| 大标题 | 居中加粗 18pt,不进 Heading | 普通段落 + alignment CENTER(无 pStyle) |
| 章标题 | Heading1,三号加粗,导航可见 | `add_paragraph(style="Heading 1")` + 覆盖样式 + outlineLvl:0 |
| 题注 | 黑体小四 12pt,居中 | `apply_font(r, ("黑体","Times New Roman",12,True))` |
| 表格 | 小四 12pt,表头底色 | cell `shd fill=E8EEF5` |
| 页脚页码 | 小五 10.5pt,居中,无页眉 | footer + PAGE 域(`add_field`) |
| 横版图 | 分节符(竖→横→竖) | `section.orientation=LANDSCAPE` + 交换 width/height |

## 中英分体字体(关键)

中文与英文字符必须不同字体,否则混排难看。用 font 对象形式同时设:

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

def apply_font(run, spec):
    """spec = (中文字体, 英文字体, 字号pt, 加粗)"""
    cn, en, size_pt, bold = spec
    run.font.size = Pt(size_pt); run.font.bold = bold; run.font.name = en
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts"); rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), en); rfonts.set(qn("w:hAnsi"), en); rfonts.set(qn("w:eastAsia"), cn)

# 用法
r = p.add_run(text); apply_font(r, ("仿宋_GB2312", "Times New Roman", 16, False))
```

**坑**:只设 `font: "仿宋_GB2312"`(字符串)会让英文字符也用仿宋。必须用对象形式分体。

## 标题用 Heading 1 样式(否则无导航)

章标题必须用 `add_paragraph(style="Heading 1")` + 在 styles 覆盖 Heading 1 样式(outlineLvl:0)。否则导航窗格标题栏为空。

```python
# 覆盖 Normal 与 Heading 1 样式: 中英分体三号、Heading1 加粗 + outlineLevel:0
def configure_styles(doc):
    normal = doc.styles["Normal"]
    normal.font.size = Pt(16); normal.font.name = "Times New Roman"
    _set_rfonts(normal.element, "仿宋_GB2312", "Times New Roman")
    _set_spacing(normal.element, line=360, line_rule="auto")          # 默认 1.5 倍

    h1 = doc.styles["Heading 1"]
    h1.font.size = Pt(16); h1.font.bold = True; h1.font.name = "Times New Roman"
    _set_rfonts(h1.element, "仿宋_GB2312", "Times New Roman")
    _set_spacing(h1.element, line=360, before=360, after=180)
    _ensure_outline_level(h1.element, 0)                              # 导航可见

# 章标题段
p = doc.add_paragraph(style="Heading 1")         # 用内置样式(已在 styles 覆盖)
p.add_run(text)                                    # 大标题用普通段落不加 style
```

文档大标题用居中加粗普通段落,**不设 Heading**(否则与章混在导航树)。

## 图:随章节、分节符、按高反算

- **随章节**:按图内容插到对应章节末尾、下一章之前,不堆附录。
- **横版图用分节符**:竖排正文 → 分节符切横排 → 图 → 分节符切回竖排。不是分页符(分页符图仍挤竖排页)。同章多图合并到一个横排 section,图间用 pageBreakBefore,避免 section 转换产生空页。
- **按高反算宽**:图高 ≤ 横排可用高 - 题注高 - 余量(A4 横排可用高约 602px,图高限 520px),保证图+题注同页。

```python
# 横排 A4: 设 orientation + 手动交换 width/height (python-docx 不自动交换)
from docx.enum.section import WD_ORIENT
from docx.shared import Mm, Cm
section.orientation = WD_ORIENT.LANDSCAPE
section.page_width  = Mm(297)   # 横排宽 (竖排 210, 横排交换)
section.page_height = Mm(210)   # 横排高
section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Cm(2.54)
```

## 题注:SEQ 自动编号 + REF 交叉引用(lxml 生成期直构造)

题注用自动编号域,正文引用用交叉引用域指向题注书签。增删图/调序后全选 F9 自动同步。

### 复杂域三段式直构造(python-docx + lxml)

复杂域 = fldChar begin / instrText / separate / 缓存值run / end。用 lxml `OxmlElement` 在**生成时**直接构造,缓存值 run 带正确 rPr(题注黑体小四、正文仿宋三号),SEQ 域缓存值外包书签 `_Ref_figN`,REF 域指向该书签。**不走"空 SimpleField 占位 + 后处理正则替换"两段式**。

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def add_field(paragraph, instr, cached_value, font_spec, bookmark=None):
    def add_run():
        r = paragraph.add_run(); apply_font(r, font_spec); return r
    # begin: 带 w:dirty="true", Word 打开主动提示更新域(降低忘按 F9 的误操作)
    r = add_run()
    fld = OxmlElement("w:fldChar"); fld.set(qn("w:fldCharType"), "begin"); fld.set(qn("w:dirty"), "true")
    r._r.append(fld)
    # instrText (前后留空格 + xml:space=preserve)
    r = add_run()
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = " " + instr.strip() + " "
    r._r.append(it)
    # separate
    r = add_run()
    fld = OxmlElement("w:fldChar"); fld.set(qn("w:fldCharType"), "separate"); r._r.append(fld)
    # bookmark start (仅 SEQ 域, 包裹缓存值供 REF 定位)
    if bookmark:
        bid, bname = bookmark
        bs = OxmlElement("w:bookmarkStart"); bs.set(qn("w:id"), str(bid)); bs.set(qn("w:name"), bname)
        paragraph._p.append(bs)
    # 缓存值 run (带 rPr)
    r = add_run()
    t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve"); t.text = str(cached_value); r._r.append(t)
    if bookmark:
        be = OxmlElement("w:bookmarkEnd"); be.set(qn("w:id"), str(bid)); paragraph._p.append(be)
    # end
    r = add_run()
    fld = OxmlElement("w:fldChar"); fld.set(qn("w:fldCharType"), "end"); r._r.append(fld)

# 题注: "图 " + SEQ域(书签 _Ref_figN) + "  名称"
add_field(p, "SEQ Figure \\* ARABIC", str(seq), CAP_FONT, bookmark=(1000+seq, f"_Ref_fig{seq}"))
# 正文引用: REF 域指向书签
add_field(p, f"REF _Ref_fig{n} \\h", str(n), BODY_FONT)
# 页脚页码: PAGE 域
add_field(p, "PAGE", "1", FOOTER_FONT)
```

### 历史坑(已从源头消除,记录备查)

旧 docx-js + fix_fields.py 两段式踩过的坑,迁移 python-docx 后从源头消除:

- **SimpleField 缓存值无 rPr**:docx-js `SimpleField("SEQ ...", "1")` 缓存值 run 无 rPr,继承默认仿宋三号与题注黑体小四不一致。现 lxml 直构造,缓存值 run 自带 rPr。
- **后处理正则跨行贪婪吞 SEQ 域**:旧 fix_fields.py 用正则替换占位 `【FIGREF N】`,需否定向前限定 rPr 边界才不吞 SEQ(否则"SEQ 替换4个结果只剩1个")。现无后处理无正则。
- **skill unpack/pack 合并 run 破坏复杂域**:旧两段式经 pack 重序列化丢域(SEQ 丢失、段落减半)。现单脚本生成,不经 unpack/pack。

## Transitional schema 陷阱(validate.py 用 ISO-IEC29500-4_2016 Transitional)

本 skill vendored 的 validate.py(在 `scripts/validate/`)用 **Transitional** schema 校验。python-docx 默认输出与该 schema 命名/顺序有差异,踩坑(validate 报错但 Word 能打开):

1. **表格对齐用 `w:jc` 不是 `w:tblJc`**。CT_TblPrBase 序列里表格对齐元素叫 `jc`(CT_JcTable),不是 `tblJc`。python-docx 的 `table.alignment` setter 写 `tblJc`,Transitional schema 拒(报 "tblJc not expected, expected jc")。**解法**:手动 `OxmlElement("w:jc")` 插入,不用 setter。
2. **CT_TcMar / CT_TblBorders 子元素顺序是 `top, start, left, bottom, end, right`**(left 必须在 bottom 之前,start/end 可选跳过)。写成 `top, bottom, left, right`(bottom 在 left 前)会报 "left not expected, expected end/right"。**解法**:子元素按 `top, left, bottom, right[, insideH, insideV]` 顺序 append。
3. **tblPr/tcPr 子元素整体顺序约束**(CT_TblPrBase: tblW → jc → tblCellSpacing → tblInd → tblBorders → shd → tblLayout → tblCellMar → tblLook)。python-docx 默认 tblPr 已含 tblLook(末尾),手动加的 tblW/jc/tblBorders 必须插到 tblLook 之前,否则顺序错。**解法**:用 `insert_ordered(parent, elem, ORDER)` 按 schema 顺序表插入,不依赖 append(append 会落到 tblLook 之后违规)。

完整顺序表(TBLPR_ORDER / TCPR_ORDER)与 insert_ordered 实现见 `scripts/gen_docx.py`。

## 排版检查清单

- [ ] 中英分体字体(中文仿宋、英文 Times New Roman,apply_font 对象形式)
- [ ] 正文三号、1.5 倍行距、显式 lineRule auto
- [ ] 章标题用 Heading 1 样式 + outlineLvl:0(导航窗格可见)
- [ ] 大标题居中、不进 Heading
- [ ] 图随章节,非堆附录
- [ ] 横版图用分节符(竖→横→竖),同章多图合并一个横排 section
- [ ] 图按高度反算宽,图与题注同页
- [ ] 题注 SEQ 自动编号域 + 黑体小四 + 居中,域带 w:dirty
- [ ] 正文引用用 REF 交叉引用域指向题注书签 _Ref_figN,域带 w:dirty
- [ ] 首页空白
- [ ] 页脚页码(无页眉)
- [ ] 表格表头底色;表格对齐用 w:jc(非 tblJc)、tcMar 子元素 top,left,bottom,right 顺序
- [ ] validate.py 通过(Transitional schema)

---

# 附录:中文 Word 文档排版规范详解

> 本附录按 GB/T 9704-2012《党政机关公文格式》及中文技术报告通用惯例整理,
> 每条标注【公文】(GB/T 9704 强制项)或【通用】(技术报告常见惯例,非强制)。
> 数值均给出可直接填入 Word 的具体值。
> 实现以 python-docx 为准(见 SKILL.md 工作流与 gen_docx.py);散见的 docx-js 提示为迁移前写法,仅作 OOXML 原理对照。

## 1. 字体字号

### 1.1 公文标准(GB/T 9704-2012)

| 用途 | 中文字体 | 英文/数字字体 | 字号 | 备注 |
|---|---|---|---|---|
| 密级、紧急程度 | 黑体 | Arial | 三号(16pt) | 顶格标识,发文机关标识上方 |
| 发文机关标识(红头) | 方正小标宋简体 | — | 限定 25mm×15mm 红线之上 | 红色,居中 |
| 发文字号 | 仿宋_GB2312 | Times New Roman | 三号(16pt) | 居中 |
| 签发人 | 仿宋_GB2312 | Times New Roman | 三号(16pt) | "签发人:" 楷体,姓名黑体 |
| 标题(正文标题) | 方正小标宋简体 | — | 二号(22pt) | 红色或黑色,居中 |
| 正文 | 仿宋_GB2312 | Times New Roman | 三号(16pt) | 默认 |
| 一级标题(一、) | 黑体 | Arial | 三号(16pt) | 不加粗 |
| 二级标题((一)) | 楷体_GB2312 | Times New Roman | 三号(16pt) | 不加粗 |
| 三级标题(1.) | 仿宋_GB2312 加粗 | Times New Roman | 三号(16pt) | |
| 四级标题((1)) | 仿宋_GB2312 | Times New Roman | 三号(16pt) | |

### 1.2 通用技术报告

| 用途 | 中文字体 | 英文/数字字体 | 字号(pt) | docx-js halfPoints |
|---|---|---|---|---|
| 文档大标题 | 黑体 | Times New Roman | 18(小一)或 22(二号) | 36 / 44 |
| 章标题(Heading1) | 黑体 | Times New Roman | 16(三号) | 32 |
| 节标题(Heading2) | 黑体 | Times New Roman | 15(小三)或 14(四号) | 30 / 28 |
| 小节(Heading3) | 黑体 或 楷体 | Times New Roman | 14(四号) | 28 |
| 正文 | 仿宋_GB2312(或宋体) | Times New Roman | 16(三号) | 32 |
| 表内文字 | 宋体(优先)或仿宋 | Times New Roman | 12(小四) | 24 |
| 图题/表题(图1-1、表2-1) | 黑体 | Times New Roman | 12(小四) | 24 |
| 图注、表注 | 楷体 | Times New Roman | 10.5(五号) | 21 |
| 页码 | 宋体 或 Times New Roman | Times New Roman | 10.5(小五)或 12(小四) | 21 / 24 |
| 页眉 | 宋体 | Times New Roman | 9(小五)或 10.5(五号) | 18 / 21 |
| 脚注尾注 | 宋体 | Times New Roman | 9(小五) | 18 |

### 1.3 关键规则

1. **公文红色标题仅限公文场景**。【公文】红头 + 方正小标宋是党政机关公文独有;技术报告/办法/规定标题用黑色,字号可放大。
2. **公文强制 16pt(三号)正文**。【公文】正文每页 22 行、每行 28 字,正文必须三号不得缩小,字号违规在公文评审计分会被扣分。
3. **中英分体不能省**。Times New Roman 用于所有英文/数字;即使是公文里的发文字号"国发〔2024〕5号"中,数字也用 Times New Roman,与汉字仿宋混排时不会顶格。
4. **黑体用于强调,不用作正文**。黑体笔画粗,大段黑体阅读疲劳,通常仅用于标题、题注、表头等小段文字。
5. **楷体仅用于二级标题或引文**。【公文】楷体_GB2312 用于二级标题(以"(一)"开头);引文也可单独用楷体区别。

## 2. 标题层级

### 2.1 命名方式对比

| 层级 | 公文命名 | 通用技术报告命名 | 学位论文命名 |
|---|---|---|---|
| 第一级 | 一、 | 第 1 章 / 1 | 第 1 章 |
| 第二级 | (一) | 1.1 | 1.1 |
| 第三级 | 1. | 1.1.1 | 1.1.1 |
| 第四级 | (1) | 1.1.1.1 | 1.1.1.1 |

### 2.2 关键规则

1. **公文用汉字序数,不用阿拉伯数字**。【公文】一级标题写作"一、"、"二、"、"三、",二级"(一)"、"(二)",三级"1."、"2.",四级"(1)"、"(2)"。**严禁阿拉伯数字作一级标题**(例如"1. xxx"在公文里不合规)。
2. **技术报告首选阿拉伯数字多级编号**。【通用】"1"、"1.1"、"1.1.1" 便于自动编号 + 自动目录,且插入新节时无需手动重排。**Heading 1/2/3 + 多级列表绑定**实现。
3. **办法/规定类常用混合命名**。【通用】"第一章 总则"作为一级标题,二级用"一、",三级用"(一)",四级用"1."——这种命名在规范性文件中常见,与纯技术报告不同。
4. **标题序号后空 1 字符**(中文)或 1/4 em(英文)。**不允许**直接紧跟汉字,例如写"一、总则"是错的,应"一、 总则"或"一、\t总则"(用 tab 自动对齐)。
5. **Heading 样式与 Word 导航窗格的关系**:Word 的导航窗格只识别具有 outlineLevel 的段落(即内置 Heading 1-9 或自定义 outlineLevel 0-8)。**手动"加粗 + 放大字号"的伪标题不会被识别**。docx-js 必须在 `paragraphStyles` 中精确覆盖 `id: "Heading1"` 样式并设 `outlineLevel: 0`,否则生成文档导航窗格为空。
6. **目录需绑定到 Heading 样式**。插入目录时选"自动目录"→"自定义目录"→"目录依据样式"选 Heading 1-3,**不要选"大纲级别"**;改样式后右键"更新域"。

### 2.3 多级编号配置(Word 手动 / docx-js)

公文"一、 (一) 1. (1)"自动生成方法:

```
一级: 格式 "一、", 起始 1, 位置 左对齐, 编号之后  制表符
二级: 格式 "(一)", 起始 1, 位置 左对齐, 编号之后  制表符
三级: 格式 "1.",  起始 1, 位置 左对齐, 编号之后  空格
四级: 格式 "(1)", 起始 1, 位置 左对齐, 编号之后  空格
```

docx-js 通过 `numbering` 配置 multilevel list,每级 numberFormat 分别设为 `chineseCounting`(一级)、`(一)` 等。建议公文**手写汉字序数**而不是用自动多级列表,避免公文评审计分时"是否使用自动域"被卡。

## 3. 段落

### 3.1 公文标准

| 项 | 规范 |
|---|---|
| 首行缩进 | 2 字符(每个汉字 1 字符,即 2 个汉字宽度,约 32pt) |
| 行距 | 固定值 28 磅(每页固定 22 行) |
| 段前段后 | 0(公文不允许段前段后距,统一紧凑) |
| 对齐 | 两端对齐(justify) |
| 字间距 | 加宽 0.5 磅(部分公文编辑规范) |

### 3.2 通用技术报告

| 项 | 规范 |
|---|---|
| 首行缩进 | 2 字符(同公文) |
| 行距 | 1.5 倍行距, 或固定值 20-24 磅 |
| 段前段后 | 标题前后 0.5-1 行;正文段后 0(连续段) |
| 对齐 | 两端对齐(中英文均适用) |
| 段内不分页 | 勾选"与下段同页"、"段中不分页"防孤行 |

### 3.3 关键规则

1. **首行缩进必须是 2 字符,不是 2cm 或 16pt**。Word 中设字符单位:右键段落 → 缩进 → 特殊格式 → 首行缩进 → 2 字符。docx-js 中设 `indent: { firstLineChars: 200 }`(单位 1/100 字符,即 2 字符 = 200)或 `firstLine: 640`(三号字 2 字符 = 32pt = 640 半点)。
2. **公文用固定行距,不用倍数**。【公文】"固定值 28 磅"是 GB/T 9704 强制项,因为固定行距能保证每页固定 22 行;**倍数行距在公文评审计分会被扣分**。技术报告可用 1.5 倍或固定值 20 磅。
3. **docx-js 行距必须显式 lineRule: "auto"**。若只设 `spacing: { line: 360 }`,Word 会按默认值渲染成"单倍行距"且不警告。`{ line: 360, lineRule: "auto" }` 才是 1.5 倍。
4. **段前段后不要给正文加空行**。习惯性在每段后加 `spacing.after: 240`(12pt)会让文档"看上去像 PPT";中文公文尤其忌讳,文字应紧密排列。
5. **标题上下间距与正文不同**。章标题可设段前 12pt、段后 6pt,与正文区分;但同一章内各节标题应统一。
6. **孤行控制**:Word 默认"孤行控制"开,可勾选"段中不分页"(Keep with next)和"与下段同页"(Keep lines together)避免标题孤悬页底或段落单行换页。

## 4. 图

### 4.1 图编号

| 编号格式 | 使用场景 | 例子 |
|---|---|---|
| 图 1 | 全文统一编号,简单文档 | 图 1、图 2 |
| 图 1-1 | 分章编号,常见于技术报告、办法 | 图 1-1、图 2-3 |
| 图 2.1 | 学位论文、部分国标 | 图 2.1、图 3.5 |
| 图 1.1.1 | 极少用,长文档章节超过两位数时 | — |

**推荐**:技术报告/办法/规定用 **图 X-Y**(章-序号),最便于交叉引用且不重复。

### 4.2 关键规则

1. **题注位置必须在图下方**,与图同页居中。【通用】图与题注之间空 0.5 行(图 6pt 段后);图与题注**不拆页**(设"段落属性 → 换行和分页 → 与下段同页")。
2. **题注字体:黑体小四(12pt),居中**。【通用】中文"图 X-Y"用黑体,英文与数字"Figure 2-3"用 Times New Roman(分体)。
3. **图编号必须用 SEQ 域,不能手敲数字**。【核心】手敲"图 1-1"在增删图后全部错位;用 Word 域 `SEQ Figure \* ARABIC \s 1`(`\s 1` 表示按 Heading1 章节重置编号)自动编号。python-docx 生成时用 lxml 直接构造 SEQ 域 + 书签 `_Ref_figN`(见 gen_docx.py `add_field`),无需占位与后处理。
4. **正文引用用 REF 域**。正文写"如图 1-2 所示",这里的"图 1-2"应是 REF 域指向 `_Ref_fig2` 书签;增删图后全选 F9 自动同步。
5. **图按内容随章节,不堆附录**。【通用】常见错误:把所有图放最后一章"附图",违反"图随文走"原则,也违反 GB/T 1.1、GB/T 7713 等编辑标准。
6. **大图横排用分节符(竖→横→竖),不用分页符**。【关键】分页符在竖排页内插大图,图被裁剪或压扁;必须用"下一页"分节符 + section properties 设 landscape。docx-js:同一章多张横图**合并一个横排 section**,图间用 pageBreakBefore,**避免每个图都切一次 section**(否则中间出现空白页)。
7. **小图(宽度 < 半页)内联,不切横排**。内联图保持竖排节、设居中(`jc: "center"`)、前后各空 0.5 行。**大图(宽幅架构图等)走横排分节符;小图(图标/方图/竖图)直接正文内联,不打断竖排流。** 判别:宽高比 > 1.3 走横排,否则内联;也可在配置里逐图显式指定 `layout: "landscape" | "inline" | "auto"`。docx-js:`figParagraphLandscape(file)`(横排,按高反算宽≤520px) vs `figParagraphInline(file)`(内联,按竖排版心宽≤530px、高≤480px)。
8. **图居中 + 嵌入型(Inline)**。【通用】图用嵌入型(inline)而非四周型(wrap)或紧密型(tight);四周型在两端对齐的正文里会让首行缩进错位,且后续文本可能绕过图片。
9. **图宽反算**:固定高 ≤ 520px(A4 竖排可用宽 ≈ 750px 反算),保证图 + 题注同页不被推到下一页。
10. **图的来源标注**:数据来源或截图出处放在题注下方 1 行,字号比题注小 1 级(10.5pt 五号),用楷体,前缀"数据来源:"或"注:"。

## 5. 表

### 5.1 表编号

与图编号规则一致:**表 X-Y**(章-序号),不与图混编(`SEQ Table`)。

### 5.2 关键规则

1. **表题位置在表上方**,与图相反。【通用】表 1-1 在表格上面,黑体小四(12pt)居中;表内字号小四(12pt)。
2. **三线表规范**:仅保留顶线、栏目线、底线三条横线,其余内部无横线(必要时用无边框辅助分隔)。Word 中:全表边框设为"无",手动在表头行加上下边框,末行加下边框。
3. **表头底色**:浅灰(HEX `#E8EEF5`)或浅蓝(HEX `#D9E2F3`),不加粗文字;不要用深底色 + 白字(打印不清)。docx-js:每个表头单元格加 `shading: { fill: "E8EEF5" }`。
4. **数字列右对齐,文字列左对齐,标题列居中**。三线表内默认对齐方式混乱是最常见错误;需手动设列对齐,不要全表居中。
5. **表跨页处理**:大表跨页时,第二页自动重复表头(Word:表属性 → 行 → 勾选"在各页顶端以标题行形式重复出现");不要每页重复表号。
6. **表注**:表下方 1 行,字号五号(10.5pt),楷体,内容如"注:数据来源 XXX;N=200;*** p<0.001"。**不要把表注写在表内单元格底部**。
7. **表内禁用空格对齐**。【常见错误】用全角空格把列对齐,改字段长度后全部错位;必须用表格自身的列宽和单元格对齐。
8. **数字千分位**:表内数字超过 4 位用千分位(如 1,234),保留 2 位小数;单位写在表头(如"金额(万元)")而非每行重复。
9. **单元格内边距**:默认上/下 0.5pt、左/右 1.05pt,可统一调为上下 3pt 左右 5pt 增加留白。

## 6. 页面

### 6.1 页边距

| 文档类型 | 上 | 下 | 左 | 右 | 装订线 |
|---|---|---|---|---|---|
| 公文 GB/T 9704 | 37mm(3.7cm) | 35mm(3.5cm) | 28mm(2.8cm) | 26mm(2.6cm) | 0 |
| 公文(带装订线) | 37mm | 35mm | 28mm | 26mm | 左 10mm |
| 通用技术报告 A4 | 2.54cm(1 英寸) | 2.54cm | 3.18cm(1.25 英寸) | 3.18cm | 0 |
| 学位论文 | 3cm | 2.5cm | 3cm | 2.5cm | 0 |
| 书籍 | 2.5cm | 2.5cm | 2.5cm | 2.5cm | 0(无线装订) |

### 6.2 关键规则

1. **公文页边距数值精确到 mm**。【公文】GB/T 9704 上 37 下 35 左 28 右 26mm 是固定值,不允许随便改;评审计分工具会用标尺测量。
2. **页码字号与字体**。【公文】页码用 4 号半(14pt)宋体阿拉伯数字,数字左右各加 4 号半小圆点(如"-1-");通用技术报告用小五(10.5pt)Times New Roman 居中或外侧对齐。
3. **页码位置**。【公文】单页码右页码居右空 4 字,双页码左页码居左空 4 字;即奇页右对齐、偶页左对齐。**首页不显示页码**(正文从第二页起编 1)。【通用】技术报告常用居中、奇偶相同。
4. **页眉**:技术报告常设页眉(章节名 + 文档名),五号宋体居中;**公文一般无页眉**(除非涉密标识)。
5. **奇偶页不同**设置:文档 → 布局 → 页面设置 → 版式 → 勾选"奇偶页不同"→ 页脚分别设奇页/偶页页码位置。docx-js:section properties 设 `<w:evenAndOddHeaders/>` + 分别定义 defaultHeader / evenHeader。
6. **首页不同**:封面页与正文页用分节符断开(下一页分节符),首页不设页码或设为 0;第二节开始计 1。
7. **横排 A4** 尺寸:宽 297mm × 高 210mm(竖排是 210×297,横排交换);页边距通常设为上下 2cm、左右 2.5cm。
8. **纸张大小**:默认 A4(210×297mm)。上报国务院的公文用 A3 或 16K;国务院 2013 年规定公文统一用 A4 纸。

### 6.3 封面与正文分节

1. **封面必须用分节符**断开,而不是分页符。【关键】分页符继承前节的页码、页眉、页边距;分节符可重置页码、重设页边距。
2. **封面节**:不显示页码;可设不同的页边距(如封面四周边距 4cm);可不计入正文页数。
3. **目录节**:可在节属性中设页码用罗马数字 I、II、III;正文节改用阿拉伯数字 1、2、3。
4. **附录节**:可在节属性中重置页码起始(附录 A 重新从 A-1 开始)。

docx-js:

```javascript
sections: [
  { properties: { page: { size: {...}, margin: {...} }, titlePage: true }, children: [/* 封面 */] },
  { properties: { page: { size: {...}, margin: {...}, pageNumber: { start: 1 } } }, children: [/* 目录 */] },
  { properties: { page: { size: {...}, margin: {...}, pageNumber: { start: 1, format: "decimal" } } }, children: [/* 正文 */] },
]
```

## 7. 目录

### 7.1 关键规则

1. **目录必须由 Heading 样式自动生成**,不手敲页码。【核心】手敲目录是中文文档返工率最高的错误之一;每次修改都必须手动改页码和文字。
2. **目录字体**:标题(如"目录")用黑体三号(16pt)居中;目录条目用宋体(或仿宋)小四(12pt);一级条目加粗,二级三级不加粗。
3. **目录条目与页码之间用"……"虚点连接**(Word 自动),不是连续点点也不是全角省略号。
4. **目录条目缩进**:一级不缩进,二级缩进 1 字符,三级缩进 2 字符。docx-js 自动目录通过 `TableOfContents` 的 styles 选项控制。
5. **目录深度**:技术报告 3 级;学位论文 4 级;公文通常 2 级(一、(一))。
6. **页码右对齐,带前导符**(Tab 字符 + 点引导)。
7. **生成后必须 F9 更新**。域默认显示上次缓存值,新增章节不会自动出现在目录里。
8. **目录占 1-2 页**,附在正文前;不要把目录塞进封面背面同一页。

docx-js:

```javascript
new TableOfContents("目录", {
  hyperlink: true,
  headingStyleRange: "1-3",
  stylesWithLevels: [
    { styleName: "Heading1", level: 1 },
    { styleName: "Heading2", level: 2 },
    { styleName: "Heading3", level: 3 },
  ],
})
```

## 8. 其他细节

### 8.1 脚注与尾注

1. **脚注**:每页底部,序号 ①②③(自动编号);正文用上标编号引用。
2. **尾注**:全文末尾(参考文献前),序号 i ii iii(罗马数字)或 1 2 3;**学位论文常用**。
3. **脚注线**:正文与脚注之间自动 1/3 页宽横线;不要手动加。
4. **脚注字号**:宋体 9pt(小五),中文宋体英文 Times New Roman。
5. **脚注引用**:上标编号(默认),不要用括号包裹。

### 8.2 公式编号

1. **公式居中,编号右对齐**(如 `(2-3)`,章-序号);Word 用制表位实现:1 个居中制表位 + 1 个右对齐制表位。
2. **公式编号外加圆括号**,不加点:`(2-3)` 而非 `2-3`。
3. **公式字体**:Times New Roman 斜体(变量)、正体(数字、函数名如 sin、log);中文说明用宋体。
4. **长公式换行**:在运算符后换行,不要在数字/变量中间断开。

### 8.3 数字与单位

1. **数字与单位之间空 1/4 汉字**(`5 kg`、`20 °C`),不写"5kg"。
2. **百分号**:与数字连写(`50%`),不空格。
3. **中文数字 vs 阿拉伯数字**:公文里"一、二、三"作序数,"1、2、3"作统计数字;不要混用。
4. **数字范围**:用"~"或"—",**不要用半角连字符 `-`**(`5~10 °C`,不写 `5-10°C`)。
5. **千分位**:4 位以上用千分位(`,`),4 位不用(`1234`,不写 `1,234`)。
6. **概数**:相邻两个数字连写表示概数(`二三米`、`十七八岁`),不写"`2、3 米`"。

### 8.4 标点

1. **中文标点用全角**(`，。、；：""''！?`),**不与英文混用**。
2. **中英文混排空格**:英文/数字与中文之间空 1/4 汉字(约 0.5 个字符),不是 1 个空格也不是没有空格。`比如使用 Python 编程` 中 "Python" 左右各空 1/4 字符,显示更整齐。
3. **引号**:中文用 `""''(弯引号)`,不直引号 `""''`。
4. **括号**:中文内容用全角括号 `()`,英文内容用半角 `()`。
5. **省略号**:中文用 6 个点 `……`(占 2 字宽),不是 3 个点 `...`。
6. **破折号**:中文用 2 个三杠 `——`(占 2 字宽),不是英文 hyphen `-`。
7. **顿号**:并列的汉字之间用 `、`;并列的英文/数字之间用 `,`(逗号)。

### 8.5 英文/数字字体(中英分体)

1. **正文中所有英文与数字必须用 Times New Roman**(或 Arial),与中文仿宋_GB2312/SongTi 分体。
2. **docx-js 必须用对象形式**:`font: { ascii: "Times New Roman", hAnsi: "Times New Roman", eastAsia: "仿宋_GB2312" }`。**只设字符串 `font: "仿宋_GB2312"` 会让英文也变成仿宋**(极常见错误)。
3. **表格、题注、页码中的英文/数字同样分体**。
4. **代码片段**:若是等宽代码(英文/数字),单独用 Consolas / Courier New,与正文区分。

## 9. 常见错误清单(导致返工)

> 这些是中文 Word 文档排版中最常见的、会引起返工的问题。每条给出问题描述、原因、解法。

### 9.1 编号与题注

1. **手敲题注号不用域**。问题:写"图 1-1",数字手敲,中间删一张图后所有图编号错位。**解法**:用 `SEQ Figure \* ARABIC \s 1` 域 + 书签;改后全选 F9 同步。
2. **图与表编号混用同一 SEQ**。问题:删图后表编号从 5 跳到 3,因为图用了同一个 SEQ。**解法**:图用 `SEQ Figure`,表用 `SEQ Table`,分开计数。
3. **目录与正文页码不一致**。问题:手敲目录页码,改了正文后目录不更新。**解法**:用 `TOC` 域生成目录,改后右键"更新域"。
4. **三级以下用汉字序数"1.1.1"**。问题:层级超过 3 后,汉字序数(第一章 → 第一节 → 第一小节)不可行,但混用阿拉伯与汉字容易乱。**解法**:统一用阿拉伯数字多级列表。

### 9.2 字体字号

5. **中英不分体**。问题:整个文档英文也用仿宋_GB2312,英文比例高时难读;或在 Word 中手动把 Times New Roman 改成宋体,改后英文变宋体。**解法**:所有 run 用 font 对象 `{ascii, hAnsi, eastAsia}` 同时设。
6. **正文用二号字显得"正式"**。问题:正文 22pt 撑爆每页只能放几行。**解法**:正文固定三号(16pt);只把大标题放大。
7. **小标题用"加粗 + 放大"伪标题**。问题:Word 导航窗格不识别,无法生成目录。**解法**:用内置 Heading 1/2/3 样式,不要手动加粗字号。

### 9.3 段落与样式

8. **段后空 12pt 强行分段**。问题:把每段之间加空行,看上去像 PPT 而非文档。**解法**:正文段后 0;靠标题区分章节。
9. **行距用 1.0 倍**。问题:正文拥挤、批注插不进。**解法**:技术报告 1.5 倍或固定 20 磅;公文固定 28 磅。
10. **首行缩进用厘米不用字符**。问题:换字号后缩进不一致(2cm 在三号字是 4 字符,在小四字是 5 字符)。**解法**:用"首行缩进 2 字符"单位,字符随字号自动调整。

### 9.4 图与表

11. **图堆到最后一章附图**。问题:翻到附录才能看图,正文理解断裂。**解法**:图随章节,第一次引用该图的章节内插图。
12. **横版大图用分页符不是分节符**。问题:分页符不会改页面方向,大图被压扁或裁剪。**解法**:分节符(下一页)+ section properties orientation LANDSCAPE。
13. **题注被推到下一页**。问题:图占满本页底部,题注跳到下一页,看起来分离。**解法**:图高反算(图 ≤ 520px),保证图+题注同页;或缩小图高。
14. **表内用空格对齐**。问题:删一列或加宽一列,所有列错位。**解法**:用真正的表格(Insert Table);各列设固定宽度;数字列右对齐。
15. **表题与表编号反着放**。问题:有人把表号放表下方,与图混。**解法**:**表号放表上方,图号放图下方**——这是 GB/T 7713 等编辑标准的强制规定。
16. **三线表加竖线分隔内部**。问题:加竖线后表不叫三线表,且竖线在不同行高度不一致。**解法**:严格三线:仅顶线、栏目线、底线三条横线。

### 9.5 页码页眉

17. **页码不连续**。问题:中间某页因分节符没设"续前节",页码从 1 重启。**解法**:分节符"下一页"后,在新节属性里设页码"续前节"(不勾"重新开始编号")。
18. **奇偶页页码位置错**。问题:勾了"奇偶页不同"但忘了在偶数页设左对齐页码,导致奇偶页码都居右。**解法**:分别编辑奇页/偶页的页脚。
19. **首页出现页码**。问题:封面也被算第 1 页。**解法**:封面用分节符断开(不是分页符)+ 首页节属性"首页不同" + 首页页脚空。

### 9.6 标题与目录

20. **大标题与章标题都用了 Heading 1**。问题:文档大标题("XXX 办法")出现在导航窗格第一行,与"第一章"同级混乱。**解法**:大标题用普通段落 + 居中加粗,不设 Heading。
21. **目录只显示 1-2 级**。问题:Heading 3 写了很多但目录只有 Heading 1-2。**解法**:插入目录时选"自定义目录",深度设到 3 或 4。
22. **改了标题文字后目录不同步**。问题:Word 默认不自动更新域。**解法**:全选(Ctrl+A)按 F9,所有目录/题注/页码同步刷新。

### 9.7 其他常见

23. **中文文档里英文/数字不换 Times New Roman**。问题:英文段落用宋体,与中文混排难看。**解法**:见 8.5,中英分体。
24. **百分号、千分位、连字符用英文半角**。问题:`50%` 应是 `50%`(不空格),`1,234` 应是 `1,234`(千分位半角逗号),`5-10°C` 应是 `5~10 °C`。
25. **脚注/尾注字号 5 号而非小五**。问题:脚注过大会盖住正文。**解法**:脚注 9pt(小五)。
26. **公式不居中或编号不对齐**。问题:公式左对齐、编号乱放。**解法**:用 2 个制表位(居中 + 右对齐),公式在中间制表位,编号在右制表位。
27. **页面背景色 / 装饰花纹**。问题:打印出来黑乎乎,公文评审计分直接扣分。**解法**:纯白底;正式公文/办法不加任何装饰。
28. **不同章节之间用空行分段**。问题:章末加 5 个回车换页。**解法**:用"页面布局 → 分隔符 → 下一页分节符";或章标题段设"段前分页"。
29. **PDF 转 Word 后字体丢失**。问题:PDF 转 docx 后所有文字变成默认宋体或图片,排版全失效。**解法**:不要 PDF 转 Word;原始电子版直接编辑;若是扫描件 PDF,需 OCR 后人工校对(正确率一般 95% 以下)。
30. **忘记设 docx-js 默认样式**。问题:段落没设 run/paragraph defaults,Word 用默认 Calibri 11pt 显示中文,丑陋且不一致。**解法**:在 styles.default.document 显式设 run.font 和 paragraph.spacing。

---

## 附录:GB/T 9704-2012 关键数值速查

| 项 | 值 |
|---|---|
| 纸张 | A4(210 × 297 mm) |
| 上边距 | 37 mm ± 1 |
| 下边距 | 35 mm ± 1 |
| 左边距 | 28 mm ± 1 |
| 右边距 | 26 mm ± 1 |
| 每页行数 | 22 行 |
| 每行字数 | 28 字 |
| 正文字体 | 仿宋_GB2312(三号 16pt) |
| 行距 | 固定值 28 磅 |
| 标题字体 | 方正小标宋简体(二号 22pt) |
| 页码字体 | 4 号半(14pt)宋体阿拉伯数字 |
| 页码位置 | 单页右、双页左,数字左右各 4 号半小圆点 |
| 发文字号字体 | 仿宋_GB2312 三号 居中 |
| 签发人 | "签发人:"三号楷体,姓名三号黑体 |
| 抄送 | 仿宋_GB2312 四号(14pt) |
| 印发机关和印发日期 | 仿宋_GB2312 四号(14pt) |
| 密级 | 黑体三号,顶格左,前空 2 字 |
| 紧急程度 | 黑体三号,顶格右,前空 2 字 |

## 附录:Word 默认字号对照

| Word 字号 | pt | halfPoints | 常见用途 |
|---|---|---|---|
| 初号 | 42 | 84 | 公文标题(大) |
| 小初 | 36 | 72 | 封面主标题 |
| 一号 | 26 | 52 | 封面副标题 |
| 小一 | 24 | 48 | 章标题大字 |
| 二号 | 22 | 44 | 公文标题、章标题 |
| 小二 | 18 | 36 | 文档大标题、节标题 |
| 三号 | 16 | 32 | **公文正文**、章标题 |
| 小三 | 15 | 30 | 节标题 |
| 四号 | 14 | 28 | 小节标题、抄送 |
| 小四 | 12 | 24 | **题注、表内、图注** |
| 五号 | 10.5 | 21 | 表注、页脚、脚注 |
| 小五 | 9 | 18 | 页眉、注释 |

> 半磅(halfPoint)换算:`pt × 2 = halfPoints`。docx-js 字号属性以 halfPoints 为单位,如 16pt 写作 `size: 32`。

---

## 本对话修正史对应的已知问题与对策(实操验证)

> 以下问题均在生成《仿真资源管理办法》docx 的多轮修正中实际踩到并验证解决。生成前逐一对照,避免重犯。
> 迁移 python-docx 后,验证位置统一 `gen_docx.py`;fix_fields.py 已废弃(复杂域改生成期 lxml 直构造)。

| # | 问题 | 对策 | 验证位置 |
|---|---|---|---|
| 1 | 图全塞末尾附录,正文无图 | 图随章节插,在对应章末尾、下一章前插图 | gen_docx.py flush_chapter |
| 2 | 大图横排只插分页符,图仍挤竖排页 | 大图用分节符(竖→横→竖),独立横排 section | gen_docx.py ensure_landscape |
| 3 | 小图也走横排分节,过度打断 | 小图(layout:inline/auto且宽高比≤1.3)正文内联,不切横排 | gen_docx.py fig_inline_para |
| 4 | 同章多图各开横排 section,中间空页 | 同章横排图合并一个横排 section,图间用 pageBreakBefore | gen_docx.py _emit_landscape_group |
| 5 | 图过高,题注被推到下页 | 图按高度反算宽,横排高≤520px、内联高≤480px,keepNext | gen_docx.py fig_landscape_para |
| 6 | 题注序号手敲数字,增删图错位 | 题注用 SEQ 自动编号域 | gen_docx.py add_field |
| 7 | 复杂域缓存值 run 无 rPr,数字字体与题注不一致 | lxml 直构造三段式,缓存值 run 带 rPr(题注黑体小四、正文仿宋三号) | gen_docx.py add_field |
| 8 | 题注字体与正文相同 | 题注黑体小四(12pt)、居中 | gen_docx.py caption_para |
| 9 | 正文无图引用,或引用号手敲 | 正文图引用用 REF 域指向题注书签 _Ref_figN | gen_docx.py ref_para |
| 10 | 中英混用仿宋,英文难看 | apply_font 分体:ascii/hAnsi=Times New Roman、eastAsia=仿宋_GB2312 | gen_docx.py apply_font |
| 11 | 标题用加粗段落冒充,导航窗格空 | 章标题用 Heading 1 样式 + 覆盖(outlineLvl:0) | gen_docx.py h1_para / configure_styles |
| 12 | 大标题也设 Heading,与章混在导航树 | 大标题用居中加粗普通段落,不设 style | gen_docx.py title_para |
| 13 | 旧两段式经通用 unpack/pack 工具,复杂域被合并 run 破坏(SEQ 丢失、段落减半) | 迁移 python-docx 单脚本,不经 unpack/pack(已消除) | gen_docx.py |
| 14 | 旧后处理 REF 正则跨行贪婪回溯吞 SEQ 域(SEQ替换4个结果只剩1) | 迁移后无后处理无正则(已消除) | gen_docx.py |
| 15 | 行距只设 line:360,部分 Word 版本不识别 | 显式 `lineRule: "auto"`(line_spacing=1.5 自动设) | gen_docx.py set_spacing |
| 16 | 无首页空白 | 首段插 PageBreak | gen_docx.py main |
| 17 | 无页码或页码与正文同行 | 页脚居中 PAGE 域,不加页眉 | gen_docx.py set_footer_pagenum |
| 18 | 表格表头无区分 | 表头底色 E8EEF5 + 加粗 | gen_docx.py add_md_table |
| 19 | 正文无首行缩进 | 首行缩进 Pt(32)(三号2字符=640twips) | gen_docx.py body_para |
| 20 | 域无 dirty,Word 打开不提示更新,用户忘 F9 看不到同步 | 所有域 fldChar begin 带 w:dirty="true" | gen_docx.py add_field |
| 21 | Transitional schema 拒 tblJc(期望 jc)、tcMar 顺序错(left 须在 bottom 前) | 表格对齐用 w:jc;tcMar/tblBorders 子元素按 top,left,bottom,right 顺序;insert_ordered 按 schema 顺序表插入 | gen_docx.py add_md_table |

**生成前自检**:对照本表 21 条 + 上方"排版检查清单",逐项确认 gen_docx.py 配置已覆盖。

