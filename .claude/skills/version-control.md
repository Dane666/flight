---
name: version-control
description: Git 版本控制规范。每次修改代码后必须提交，遵循约定式提交格式。
version: 1.0.0
author: flight project
---

# Version Control 规范

此 skill 定义项目的版本控制规则，所有代码修改必须遵循。

## 基本原则

1. **每次代码修改完成后必须 commit**，遵循最小可验证变更原则。
2. 修改一个功能点 → 验证通过 → 提交一个 commit。
3. 禁止将多个不相关的修改打包在一个 commit 中。

## Commit Message 格式

遵循约定式提交：

```
<type>: <简短描述>

<详细说明（可选，多行）>

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Type 类型

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `refactor` | 代码重构（不改变行为） |
| `docs` | 文档变更 |
| `style` | 代码格式（不影响逻辑） |
| `test` | 添加或修改测试 |
| `chore` | 构建/工具/依赖变更 |
| `perf` | 性能优化 |

### 示例

```
feat: add version control skill

Define commit conventions and version control workflow for the project.

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Git 安全规则

- ❌ 永不修改 git config
- ❌ 永不执行破坏性或不可逆命令（`push --force`, `hard reset` 等），除非用户明确要求
- ❌ 永不跳过 hooks（`--no-verify`, `--no-gpg-sign`），除非用户明确要求
- ❌ 永不 force push 到 main/master
- ❌ 永不使用 `commit --amend`，除非用户明确要求
- ❌ 永不提交包含凭据的文件（`.env`, `credentials.json`, 含密钥的 `config.yaml` 等）

## Commit 流程

执行 commit 前：

1. 运行 `git status` 查看所有变更
2. 运行 `git diff` 查看具体改动
3. 查看最近的 `git log` 了解历史风格
4. 添加文件到暂存区
5. 创建 commit
6. 运行 `git status` 确认 commit 成功

### 命令模板

```bash
git add <files>
git commit -m "$(cat <<'EOF'
<type>: <description>

<details>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
git status
```

## 分支策略

- `main` 为主分支
- 新功能或修复在 `main` 上直接开发（小型项目）
- 如涉及较大改动，先创建功能分支

## 禁止提交的文件

- `config.yaml`（包含凭据时）
- `.env` 文件
- `*.db`（数据库文件）
- Playwright debug 快照 (`data/trip_debug_snapshots/`)
- `output/`、`tmp/`、`tools/` 等临时目录
