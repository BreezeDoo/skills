# BreezeDoo/skills

公开的 AI coding agent skills。可通过 [cc-switch](https://github.com/farion1231/cc-switch) 或手动复制安装。

## Skills

| Skill | 说明 |
|-------|------|
| [xmind](xmind/SKILL.md) | 读写、转换 .xmind 思维导图文件（Zen + Legacy 格式），支持 JSON/YAML/Markdown/CSV/OPML 互转，无需安装 XMind。 |
| [cn-formal-docx](cn-formal-docx/SKILL.md) | 中文规范文档（docx）排版与格式规范。仿宋三号、标题分级、自动编号题注、图随章节等中文公文排版，内置 OOXML 校验。 |
| [team-skills-hub](team-skills-hub/SKILL.md) | 管理团队共享 skill 仓库（cae-share/skills）。安装/更新/提交/新建团队 skill，支持多种 harness。首次使用自动引导配置。 |

## 安装

### 方式一：cc-switch

cc-switch -> Skills 页 -> 仓库管理 -> 添加仓库：
- Owner: `BreezeDoo`
- Name: `skills`
- Branch: `main`

然后 Install / Update All 即可。

### 方式二：手动

```bash
git clone https://github.com/BreezeDoo/skills.git
cp -r skills/team-skills-hub ~/.claude/skills/
```

## License

MIT
