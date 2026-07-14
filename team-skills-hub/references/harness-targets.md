# Harness 安装目标说明

本 skill 把团队 skill 复制到各 harness 的 skill 目录。以下是各 harness 的目录和特点。

## 各 Harness 的 skill 目录

| Harness | 目录 | 备注 |
|---------|------|------|
| Claude Code | `~/.claude/skills/` | ZCode 等 CC 兼容 harness 也读这里 |
| Codex | `~/.codex/skills/` | 内有 `.system` 子目录，不要动 |
| Gemini CLI | `~/.gemini/skills/` | |
| OpenCode | `~/.config/opencode/skills/` | |
| cc-switch | `~/.cc-switch/skills/` | SSOT 源目录，需 GUI Refresh 同步数据库 |
| Cursor | `~/.cursor/skills/` | 可能不存在，需创建 |
| 自定义 | 用户指定 | 自研 harness 等 |

> Windows 上 `~` = `%USERPROFILE%`（通常 `C:\Users\<用户名>`）。Git Bash 中 `~` 和 `$HOME` 均可用。

## 安装方式：复制 vs symlink

本 skill 默认用**复制**（`cp -r`）把 skill 放到各 target 目录。

如果用户只用一个 harness 且本机没有 cc-switch，复制即可，简单可靠。

如果用户同时用多个 harness，可以考虑 symlink 减少重复：
- 选一个主目录（如 `~/.claude/skills/`）作为实际存放位置
- 其他目录 symlink 过去：`ln -s ~/.claude/skills/<name> ~/.codex/skills/<name>`

**Windows symlink 需要管理员权限或开启开发者模式**，不确定时用复制更安全。

## cc-switch 用户的特殊说明

cc-switch 的存储结构：
- **源目录**：`~/.cc-switch/skills/`（SSOT）
- **分发**：cc-switch 把源目录 symlink 到各 agent 目录
- **数据库**：`~/.cc-switch/cc-switch.db` 记录已安装 skill 和 SHA-256

如果 target 包含 `~/.cc-switch/skills/`：
- 复制文件后，cc-switch 数据库**不会自动感知**
- 需要用户在 GUI 点 **Refresh** -> **Update All**
- 数据库同步后才能在 GUI 看到

**推荐**：cc-switch 用户直接选 agent 目录（如 `~/.claude/skills/`），跳过 cc-switch 中转。cc-switch 数据库状态不同步不影响 agent 实际读取 skill。

## cc-switch 不支持私有仓库

cc-switch 下载 skill 仓库时**不带任何认证**（直接 GET `https://github.com/{owner}/{name}/archive/refs/heads/{branch}.zip`）。私有仓库返回 404，cc-switch 报「所有分支下载失败」。

这是已知限制（[farion1231/cc-switch#1213](https://github.com/farion1231/cc-switch/issues/1213)，open/stale）。

**解决**：本 skill 不用 cc-switch 的下载功能，而是用 `git clone`（走本地 gh/git 凭据）拉取仓库，再用文件系统操作分发到各 harness 目录。

## 排错

### gh 报 "GH_TOKEN environment variable is being used"

环境变量 `GH_TOKEN` 或 `GITHUB_TOKEN` 污染了 gh 的凭据选择。解决：

```bash
# 当前 session 清除
unset GH_TOKEN GITHUB_TOKEN

# 永久删除（Windows 用户级）
powershell.exe -NoProfile -Command "[Environment]::SetEnvironmentVariable('GH_TOKEN', $null, 'User')"
powershell.exe -NoProfile -Command "[Environment]::SetEnvironmentVariable('GITHUB_TOKEN', $null, 'User')"
# 删除后重启终端
```

如果不想删环境变量（比如 GH_TOKEN 是给别的工具用的），每次 gh 命令前加前缀：
```bash
GH_TOKEN= GITHUB_TOKEN= gh repo view cae-share/skills
```

### gh 无法访问 cae-share

```bash
gh auth status
```

如果显示的账号对 cae-share 没权限，重新登录并确保授权 org：
```bash
gh auth login --web
# 浏览器授权时勾选 cae-share
```

### 安装后 skill 没生效

确认 target 目录路径正确：
```bash
ls ~/.claude/skills/<skill-name>/SKILL.md
```
如果文件在但 agent 没加载，重启 agent 或检查 agent 的 skill 加载配置。

### Windows symlink 失败

用复制代替 symlink，或在 Windows 设置中开启「开发者模式」。
