# 插件仓单测

测试统一放在仓库根 `tests/` 下，**不放在插件目录内**——插件的本地同步与市场下发按
整目录拷贝（`shutil.copytree`），插件目录内的测试会被一并下发到运行时副本。

## 目录结构

```
tests/
├─ _bootstrap.py   薄壳 shim：定位同级 MoviePilot 后端入 sys.path，引导逻辑委托主程序 app/testing.bootstrap
├─ conftest.py     pytest 引导：按目标选择 v2/v3 插件环境并注册网络守卫
├─ v3/             V3 专用实现（plugins.v3/）单测
│  └─ subscribeassistantenhanced/
└─ v2/             可由 V3 主程序兼容加载的 V2 旧实现（plugins.v2/）单测
   └─ brushmanager/
```

## 运行

需要 MoviePilot 后端置于插件仓**同级目录**（或设环境变量 `MOVIEPILOT_BACKEND_PATH`），
先在主程序目录执行 `uv sync --locked`，再使用生成的 `MoviePilot/.venv/bin/python`。
两组插件测试都在 MoviePilot V3 后端运行。

```bash
# 全量（推荐入口）：CI、V3 专用实现、V3 兼容加载的 V2 旧实现依次独立运行
MOVIEPILOT_BACKEND_PATH=<workspace>/MoviePilot <workspace>/MoviePilot/.venv/bin/python tests/run.py

# 也可按轨道单独跑（v2/v3 必须分会话，勿混跑）
MOVIEPILOT_BACKEND_PATH=<workspace>/MoviePilot <workspace>/MoviePilot/.venv/bin/python -m pytest tests/v3
MOVIEPILOT_BACKEND_PATH=<workspace>/MoviePilot <workspace>/MoviePilot/.venv/bin/python -m pytest tests/v2/brushmanager
```

`tests/run.py` 把 v2/v3 放在独立子进程运行。`tests/v3` 跑 V3 专用实现；`tests/v2`
按 `package.v2.json` 动态选择未声明 `v3:false` 且已有测试、可被 V3 主程序加载的 V2 旧实现。测试目录找不到索引条目时
失败关闭，兼容名单不写死在 runner。两轨可能存在同名插件包，同一解释器进程混跑会相互覆盖。
隔离 `CONFIG_DIR`、建表、`app.helper.sites` 垫片、插件目录注入、v2/v3 marker、
autouse 网络守卫等引导逻辑统一在主程序 `app/testing`（`bootstrap` / `network_guard`）维护一处；
本仓 `tests/_bootstrap.py` 仅是「定位后端入 `sys.path`」的薄壳 shim，故后端需为含 `app/testing/bootstrap`
的较新 MoviePilot。共享 harness（`stub_modules` 等）在 bootstrap 后可直接复用。

测试必须通过生产命名空间 `app.plugins.<plugin_id>` 导入插件及子模块，不使用
顶层 `import <plugin_id>`。单一模块身份可避免事件订阅、类级状态和插件实例重复创建。

## 提 PR / push 前

先本地 `python tests/run.py` 跑**全量并确认通过**，再 push / 提 PR。

## 新增 V3 插件最低测试门禁

新插件统一进入 `plugins.v3/`，必须同时提交至少一个对应的
`tests/v3/<plugin_id>/test_*.py`。该门禁不追溯历史兼容实现；新增插件不会自动加入 A 档覆盖率门禁，达到核心维护等级后再显式写入
`plugin_quality.json`。

## 索引兼容语义

- `package.json` 的默认实现需要 `v2:true`（或显式 `v3:true`）才能进入 V3 回退链。
- `package.v2.json` 的实现默认由 V3 继承；不兼容或已有 V3 专用副本时声明 `v3:false`。
- `package.v3.json` 与 `plugins.v3/` 存放只面向 MoviePilot V3 的专用实现。
- V1/V2 历史实现仍可发布；其中未声明 `v3:false` 的 V2 实现由 V3 主程序兼容加载，测试不再针对 V2 主程序单独运行。

## 依赖清单

- V3 插件有额外依赖时使用 `pyproject.toml`，依赖写入 `[project].dependencies`。
- 插件版本由插件类与 `package.v3.json` 维护，清单使用 `dynamic = ["version"]`。
- 插件不提交 `uv.lock`；MoviePilot 不为每个插件创建独立环境，会在共享环境中统一解析和安装。
- V1/V2 历史插件继续使用 `requirements.txt`。

## 覆盖率门禁

插件覆盖率按插件独立统计，不使用全仓聚合覆盖率。历史兼容实现数量多且维护等级不同，
全量纳入 coverage 会让未接入测试的插件以 0% 拉低整体指标，也无法反映当前变更风险。

`plugin_quality.json` 声明需要强制覆盖率门禁的 A 档插件。当前默认锁定：

- `v3/subscribeassistantenhanced`

门禁阈值：

- 行覆盖率：不低于 90%
- 方法覆盖率：不低于 90%
- 新增/变更可执行行覆盖率：不低于 90%

本地快速检查（只检查总行覆盖率和方法覆盖率，不计算新增/变更行）：

```bash
env -u CONFIG_DIR MOVIEPILOT_BACKEND_PATH=<workspace>/MoviePilot \
  <workspace>/MoviePilot/.venv/bin/python scripts/plugin_coverage.py
```

如果只检查单个插件：

```bash
env -u CONFIG_DIR MOVIEPILOT_BACKEND_PATH=<workspace>/MoviePilot \
  <workspace>/MoviePilot/.venv/bin/python scripts/plugin_coverage.py --generation v3 --plugin subscribeassistantenhanced
```

CI 等价检查（包含新增/变更可执行行覆盖率）：

```bash
git fetch origin main:refs/remotes/origin/main
env -u CONFIG_DIR MOVIEPILOT_BACKEND_PATH=<workspace>/MoviePilot \
  <workspace>/MoviePilot/.venv/bin/python scripts/plugin_coverage.py --base-ref origin/main
```

新增行覆盖率基于 `--base-ref` 或环境变量 `PLUGIN_COVERAGE_BASE_REF` 计算；未传基准时只执行
总行覆盖率和方法覆盖率，新增行按 0/0 视为通过。新增行只统计 coverage 识别到的可执行语句，
注释、空行、纯声明不会影响新增行覆盖率。本地 `origin/main...HEAD` 只包含已提交 diff；
尚未提交的工作区改动不会进入新增/变更行覆盖率统计。

## 新增用例

1. V3 专用实现放到 `tests/v3/<plugin_id>/`；兼容旧实现保留在 `tests/v2/<plugin_id>/`。
   所有插件都按插件 ID 建目录，不把用例文件直接平铺在代际目录；文件名使用 `test_*.py`，
   在插件独立目录内不再重复插件名前缀；
2. 通过 `app.plugins.<plugin_id>` 生产命名空间导入插件；根 conftest 会按本次运行目标在用例导入前完成后端与插件目录注入；
3. 使用 pytest 风格编写测试：普通函数或测试类均可，断言使用 `assert`；不要新增
   `unittest.TestCase`、`unittest.main()` 或 `if __name__ == "__main__"` 入口；
4. `unittest.mock` 可以继续作为 mock 工具使用；“不用 unittest”指测试组织与执行入口不使用
   `unittest` runner；
5. 优先用 `object.__new__` 绕过插件 `__init__`，只测纯逻辑方法，避免依赖完整运行时。
