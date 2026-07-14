---
name: team-skills-hub
description: 管理团队共享 skill 仓库（cae-share/skills）。当用户想安装、更新、提交或新建团队 skill 时使用。首次使用自动引导配置。支持 Claude Code、Codex、OpenCode、Gemini、Cursor、cc-switch 等多种 harness 的 skill 目录。
---

# Team Skills Hub

管理团队共享 skill 仓库 `cae-share/skills`（GitHub Org 私有仓库）。
所有团队 skill 存放在这里，成员通过 git 拉取和提交，修改经 PR review 后合并，全员可得。

> **本 skill 本身**托管在公开仓库 `BreezeDoo/skills`，可直接分享链接。它管理的是 `cae-share/skills` 私有团队仓库。

## 何时使用

| 用户说的 | 执行 |
|---------|------|
| "装个团队的 XX skill" / "拉取 XX" | 【安装 skill】 |
| "更新 skills" / "刷新 skills" | 【更新 skill】 |
| "同步一下" / "看看有没有新 skill" | **意图模糊，先问**：安装新的还是更新已有的？ |
| "提交这个 skill" / "共享到团队" | 【提交修改】 |
| "新建一个团队 skill" | 【新建 skill】 |
| "团队有哪些 skill" | 【查看列表】 |

**安装 vs 更新的区别**：
- **安装** = 装一个本机还没有的新 skill
- **更新** = 把本机已有的 skill 刷新到仓库最新版本

## 配置文件

本 skill 的配置存放在 `~/.team-skills-hub.json`：

```json
{
  "repo_path": "<本地仓库路径>",
  "targets": ["<skill 安装目标目录列表>"]
}
```

**每次操作前**，先读这个文件。如果不存在，执行【首次配置】。

## 首次配置

按顺序引导，每步确认成功再继续：

### 1. 检查 gh CLI 登录

```bash
gh auth status
```

如果未登录，或无法访问 cae-share：
```bash
gh auth login
# 选 GitHub.com -> HTTPS -> Login with a web browser
# 授权时确保 cae-share org 被授权
```

验证能访问私有仓库：
```bash
gh repo view cae-share/skills --json name
```

> 如果 `gh auth status` 提示 "GH_TOKEN environment variable is being used"，说明环境变量污染了 gh。运行 `unset GH_TOKEN GITHUB_TOKEN` 后重试，或参考 [references/harness-targets.md](references/harness-targets.md) 的排错部分。

### 2. clone 仓库

问用户放哪（默认 `~/projects/skills`）：

```bash
git clone https://github.com/cae-share/skills.git <用户指定路径>
```

### 3. 选择安装目标

检测本机已存在的 harness 目录，向用户展示并询问装到哪些（可多选）：

| Harness | 检测路径 |
|---------|---------|
| Claude Code | `~/.claude/skills/` |
| Codex | `~/.codex/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| OpenCode | `~/.config/opencode/skills/` |
| cc-switch | `~/.cc-switch/skills/` |
| Cursor | `~/.cursor/skills/`（可能不存在，可创建） |

检测方法：逐个检查目录是否存在，把存在的列出来让用户选。同时问"有没有检测不到的 harness？可手动输入路径。"

> **cc-switch 用户**：如果选 `~/.cc-switch/skills/`，文件会被复制到这里，但 cc-switch 数据库不会自动感知，需要在 GUI 点 Refresh 同步。**推荐直接选 agent 目录**（如 `~/.claude/skills/`），跳过 cc-switch 中转。

### 4. 写入配置

把仓库路径和选定的目标目录写入 `~/.team-skills-hub.json`。

完成后告知用户：以后装/更新/提交直接跟我说就行。

## 安装 skill

从团队仓库安装一个**本机还没有**的 skill。

```
1. cd <repo_path> && git pull --ff-only
2. 列出仓库所有 skill: ls skills/
3. 读取 config 中的 targets，检查每个 target 下已有哪些 skill
4. 展示"未安装"的 skill 列表给用户选
5. 用户选定后，对每个 target 目录:
   cp -r skills/<skill-name>/ <target>/<skill-name>/
6. 告知: 已安装 <skill-name> 到以下目录: <target 列表>
```

> 安装前检查目标目录是否已有同名 skill，有则提示用户是否覆盖。

## 更新 skill

把本机**已安装**的 skill 刷新到仓库最新版本。

```
1. cd <repo_path> && git pull --ff-only
2. 读取 config 中的 targets
3. 对每个 target 目录下的每个 skill:
   - 如果仓库 skills/ 下有同名 skill，比较内容
   - 内容有差异: 用仓库版本覆盖 (rm -rf <target>/<name> && cp -r skills/<name>/ <target>/<name>/)
   - 无变化: 跳过
4. 汇报: 更新了哪几个 skill，哪些无变化
```

## 提交修改

把本机改过的 skill 提交回团队仓库，走 PR 流程。

**如果改动在仓库工作区内**（直接改了 `<repo_path>/skills/<name>/`）：
```bash
cd <repo_path>
./tools/skill-push.sh <skill-name> "<改动说明>"
```

**如果改动在 target 目录**（如 `~/.claude/skills/<name>/`）：先复制回仓库再提交：
```bash
cp -r ~/.claude/skills/<name>/ <repo_path>/skills/<name>/
cd <repo_path>
./tools/skill-push.sh <skill-name> "<改动说明>"
```

脚本自动完成：校验结构 → commit → push → 开 PR。

提交后告知 PR 链接，提醒等 review。合并后其他成员各自【更新 skill】即可获取。

## 新建 skill

```bash
cd <repo_path>
./tools/skill-new.sh <skill-name>
```

脚本会：拉 main → 建 `skill/<name>` 分支 → 从 `template/SKILL.md` 生成脚手架。

创建后引导用户填写 SKILL.md 的 description 和正文，然后执行【提交修改】。

## 查看列表

```bash
cd <repo_path> && git pull --ff-only && ls skills/
```

或直接看远端：
```bash
gh api repos/cae-share/skills/contents/skills --jq '.[].name'
```

## 注意事项

- **私有仓库**：cc-switch 的「添加仓库」功能不支持私有仓库（下载 zip 不带认证）。本 skill 通过 git clone（走本地凭据）绕过此限制。
- **安装目标改了**：换 harness 或加新 harness 时，跟 agent 说"重新配置"或直接编辑 `~/.team-skills-hub.json`。
- **提交前先 pull**：提交修改前务必 `git pull --ff-only`，避免冲突。
- **一个 skill 一个 PR**，改动聚焦。
- 安装目标的详细说明见 [references/harness-targets.md](references/harness-targets.md)
