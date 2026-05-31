# 插件仓单测

测试统一放在仓库根 `tests/` 下，**不放在插件目录内**——插件的本地同步与市场下发按
整目录拷贝（`shutil.copytree`），插件目录内的测试会被一并下发到运行时副本。

## 目录结构

```
tests/
├─ _bootstrap.py   共享引导：隔离 CONFIG_DIR + 注入后端/插件目录到 sys.path
├─ conftest.py     pytest 引导：收集前隔离 CONFIG_DIR，按目录自动打 v1/v2 marker
├─ v2/             v2 插件（plugins.v2/）单测
└─ v1/             v1 插件（plugins/）单测（当前预留骨架）
```

## 运行

需要 MoviePilot 后端置于插件仓**同级目录**（或设环境变量 `MOVIEPILOT_BACKEND_PATH`），
并使用工作区根解释器 `<workspace>/.venv/bin/python`。

```bash
# v2（默认重心）
<workspace>/.venv/bin/python -m pytest tests/v2

# v1（如有用例）——必须独立会话，勿与 v2 混跑
<workspace>/.venv/bin/python -m pytest tests/v1
```

**v1/v2 必须分开运行**：两代存在同名插件包（如 `brushflowlowfreq`、`torrentclassifier`），
同一解释器进程无法同时加载，混跑会相互覆盖。

## 新增用例

1. 放到对应代际目录（`tests/v2/` 或 `tests/v1/`），文件名 `test_*.py`；
2. 顶部调用 `prepare_v2_backend()` / `prepare_v1_backend()`（见 `_bootstrap.py`），
   必须早于首个 `import app.*` 或插件包导入；
3. 优先用 `object.__new__` 绕过插件 `__init__`，只测纯逻辑方法，避免依赖完整运行时。
