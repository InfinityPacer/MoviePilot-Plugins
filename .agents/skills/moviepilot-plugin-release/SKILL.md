---
name: moviepilot-plugin-release
description: Use when publishing, releasing, version-bumping, or preparing a pull request for a v1 or v2 plugin in the InfinityPacer/MoviePilot-Plugins repository.
---

# MoviePilot 插件发版

## 核心原则

以插件仓源码、市场元数据和 GitHub Release 的实际结果形成闭环。不得把“本地改完”、
“PR 已创建”或“Action 已触发”当成发版完成。

只操作 `InfinityPacer/MoviePilot-Plugins`。发版统一走功能分支、PR Required Check、
Auto-merge 和 `main` Release workflow，不直接 push `main`。

## 1. 确认范围

1. 运行 `git remote -v`，确认仓库是 `InfinityPacer/MoviePilot-Plugins`。
2. 运行 `git status --short --branch`，保留并避开用户已有改动。
3. v2 插件只修改 `plugins.v2/<plugin_id>/` 和 `package.v2.json`；除非用户明确要求，
   不修改 `plugins/`。
4. 若当前在 `main`，从最新 `origin/main` 创建当前代理对应的协作分支：
   - Codex：`codex/release/<plugin>-<version>`
   - Claude Code：`claude/release/<plugin>-<version>`

## 2. 同步发布事实

按以下顺序核对，不要只搜索版本字符串：

1. 插件类的 `plugin_version`；
2. `package.json` 或 `package.v2.json` 对应条目的 `version`；
3. 对应 `history["v<version>"]` 的用户可读说明；
4. 若插件存在独立 README，其顶部“版本更新日志”必须有同版本、同语义条目；
5. 插件目录、package key、插件 ID 和 `plugin_version` 必须属于同一插件。

版本说明描述发布后的当前行为，不写 commit message 视角，不写源码行号或本机信息。

## 3. 启用本地门禁

先读取现有配置：

```bash
git config --get core.hooksPath
```

- 无输出：运行 `git config core.hooksPath .githooks`。
- 输出 `.githooks`：继续。
- 输出其他路径：停止并说明冲突，不得覆盖用户已有 Hook。

随后直接运行：

```bash
.githooks/pre-push
```

版本门禁不通过时先修复，不得使用 `--no-verify` 绕过。

## 4. 验证

使用工作区 `.venv-test`，worktree 中显式指定后端：

```bash
MOVIEPILOT_BACKEND_PATH=<workspace>/MoviePilot \
  <workspace>/.venv-test/bin/python -m pytest tests/<v1|v2>/<plugin_id> -q
MOVIEPILOT_BACKEND_PATH=<workspace>/MoviePilot \
  <workspace>/.venv-test/bin/python tests/run.py -q
python .github/scripts/check_plugin_versions.py package.json package.v2.json
python -m json.tool package.v2.json >/dev/null
python -m compileall -q plugins.v2/<plugin_id>
git diff --check
```

外部服务必须 mock；全量测试不得真实出站。任何失败都要修复或明确报告，不能带失败进入 PR。

## 5. 提交前确认

展示以下内容并取得维护者明确确认后，才能 commit 或 push：

- 分支名；
- 版本同步位置；
- 测试和门禁结果；
- `git diff --stat`；
- 拟用的单行英文 Conventional Commit subject。

确认一次可以覆盖紧接着执行的 commit 和 push；用户只确认 commit 时，不得推送。

## 6. 创建并自动合并 PR

commit、push 后，用真实换行的临时 Markdown 文件创建中文 PR：

```bash
gh pr create \
  --repo InfinityPacer/MoviePilot-Plugins \
  --base main \
  --head <branch> \
  --title "<中文标题>" \
  --body-file <body-file>
```

PR 必须包含变更说明、影响路径、验证结果和协作来源。纯 Codex 写
“本 PR 为 Codex 协作提交”，纯 Claude Code 写“本 PR 为 Claude Code 协作提交”；
两者都实际参与时写“本 PR 为 Claude Code & Codex 协作提交”。

回读 PR 正文确认渲染和隐私无误，并等待 `Plugin release gate` 至少出现一次。仓库首次
启用保护时，先创建要求该检查的 `main` Ruleset，再为 PR 启用 Auto-merge；不得在
Ruleset 生效前提前启用，否则 PR 可能在没有保护条件时直接合并。

只对刚创建并核对过 URL/编号与 head SHA 的 PR 启用：

```bash
gh pr merge <pr-number> \
  --repo InfinityPacer/MoviePilot-Plugins \
  --auto --squash --delete-branch \
  --match-head-commit <head-sha>
```

不得扫描并批量启用其他 PR 的 Auto-merge，不得使用 `--admin` 绕过 Ruleset。

## 7. 回查发布

等待 PR 合并后依次确认：

1. PR 的 `mergedAt`、`mergeCommit` 和目标分支为 `main`；
2. `Plugin Release` workflow 对该 merge commit 成功；
3. tag 为 `<PluginId>_v<version>`；
4. Release 标题、说明和 zip 资产版本正确；
5. `main` 上 `package`、README 和 `plugin_version` 仍一致。

若 workflow 失败，读取失败 step 和日志，修复后重新走分支 PR；不要直接改 `main`。

## 常见错误

| 错误 | 处理 |
| --- | --- |
| 只改 package 版本 | 同步 `plugin_version`，有独立 README 时同步版本日志 |
| Required Check 一直缺失 | PR workflow 不得使用 `paths` 过滤 |
| 本地 Hook 没执行 | 检查 `core.hooksPath`，不要覆盖已有自定义路径 |
| PR 检查通过就宣称发布完成 | 继续回查合并、Release workflow、tag 和资产 |
| 为所有 PR 开启 Auto-merge | 只操作本次 skill 创建并核对过 head SHA 的 PR |
| 为赶发版使用 `--admin` 或 `--no-verify` | 修复门禁失败原因，不绕过保护 |
