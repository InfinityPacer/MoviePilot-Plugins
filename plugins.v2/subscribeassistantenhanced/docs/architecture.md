# 订阅助手（增强版）整体架构设计

## 设计目标

订阅助手（增强版）在 MoviePilot 订阅体系之上提供完成前观察、剧集待定、上映/播出暂停、下载待定、洗版编排、订阅清理、识别增强和站点证据能力。插件架构以订阅生命周期为主线，将状态归属、证据来源、资源清理和用户通知拆分为独立领域，避免入口逻辑直接组合复杂副作用。

架构约束：

- 入口层只解析事件、收集上下文并调用领域服务。
- 生命周期状态由统一生命周期层编排。
- 判定器只返回判定结果，不写订阅状态。
- writer 只维护自己负责的状态事实，不跨领域推导业务流程。
- 证据、诊断、审计和快照模块只提供输入事实，不直接拥有订阅生命周期状态。

## 订阅管理策略

增强版默认管理所有订阅，各业务域是否运行仍由现有全局开关决定。订阅管理策略只描述例外，
用于缩小管理范围或覆盖插件创建洗版订阅时的有限参数；策略不得重新启用全局已经关闭的能力。

策略按用户配置顺序从上到下匹配，第一条命中后停止，未命中时继承全局配置。首期匹配条件限定为
稳定、可解释的订阅事实：媒体身份、媒体类型、季、剧集组、订阅用户、媒体类别和订阅模式。
单条订阅规则不能只保存数据库 ID，因为分集转全集、完成后重建等流程会创建新的订阅记录；
订阅身份应由媒体来源 ID、媒体类型、季和剧集组共同确定。

媒体类别优先使用订阅显式设置的 `media_category`，没有显式值时使用识别结果中的类别。
类别无法解析时按未知类别处理并输出可诊断结果，不能假定命中某条类别规则。

首期动作限定为：

- 完全排除订阅，不再进入增强版的业务处理；
- 排除指定业务域，包括待定、暂停、完结守卫、订阅补全、洗版、下载管理、订阅清理和识别增强；
- 覆盖插件创建的全集洗版订阅保存目录，目录只能选择主程序已经配置的下载目录根路径。

保存目录覆盖不负责拼接媒体类型或类别目录。主程序负责识别精确命中的下载目录根路径，并按该目录
已有的“按类型分类”和“按类别分类”设置生成最终路径；用户指定根路径下的自定义子目录时，
主程序必须将其视为完整路径，不能再次分类。

策略解析由纯逻辑的统一组件负责，返回命中规则、允许管理的业务域和有限覆盖项。事件入口、定时巡检
和洗版编排必须复用同一解析结果，禁止在各领域散落用户名、类别或订阅 ID 判断。配置界面应提供规则
排序、当前命中订阅预览以及订阅、类别和下载目录的受控选择，不提供任意脚本或通用字段修改能力。

订阅从受管理变为不受管理时，需要执行一次状态收敛：释放增强版持有的待定和暂停归属，移除插件
下载监控与观察状态，但不得恢复外部持有的暂停状态，也不得删除下载器任务、文件、种子或整理记录。
分集转全集或完成后重建产生新订阅后，需要按稳定订阅身份重新解析策略。

## 总体结构

```mermaid
flowchart TD
    MP[MoviePilot 事件 / 链式事件 / 定时任务 / 命令] --> Entry[SubscribeAssistantEnhanced / EventProxy]

    Entry --> Lifecycle[SubscribeLifecycleCoordinator]
    Entry --> BestVersion[BestVersionOrchestrator / BestVersionConverter / PriorityManager]
    Entry --> Cleanup[SubscriptionCleanup / TorrentCleanup]
    Entry --> Recognition[RecognitionGuard]
    Entry --> Evidence[CompletionEvidencePipeline / SiteEvidence]

    Lifecycle --> Pause[PauseManager]
    Lifecycle --> PendingJudge[PendingJudge]
    Lifecycle --> PendingState[PendingStateCoordinator]
    Lifecycle --> Airing[AiringPauseChecker]
    Lifecycle --> DownloadState[download_pending 归属]
    Lifecycle --> Effects[通知 / 补搜 / 恢复保护 / 归属清理]

    Entry --> DownloadMonitor[DownloadMonitor]
    DownloadMonitor --> DownloadFacts[(下载任务索引 / hash / 超时事实)]
    DownloadState --> PendingState

    Pause --> Store[(订阅表 + 插件任务数据)]
    PendingState --> Store
    BestVersion --> Store
    Cleanup --> Store
    Evidence --> Store
```

`SubscribeAssistantEnhanced` 是插件实例和依赖组装根。`EventProxy` 是事件代理，负责把主程序事件转换为插件内部调用。生命周期、待定、暂停、下载、洗版、清理、识别和证据模块通过明确接口协作。

## 前端联邦子工程

插件前端是位于 `frontend/` 的独立 Vue 子工程，与 Python 运行时代码分离：

```text
frontend/
├── src/
│   ├── components/Config.vue
│   ├── config/
│   └── assets/
├── dist/assets/
├── package.json
├── yarn.lock
├── tsconfig.json
└── vite.config.ts
```

- `src/components/Config.vue` 负责配置页布局、用户交互和 Host 事件。
- `src/config/` 负责稳定配置键、默认值、草稿、保存 payload、字段元数据、本地化、运行概况 API 和展示规则。
- `src/assets/` 保存前端品牌资源；品牌图在联邦构建中内联，避免按宿主根路径解析。
- `dist/assets/` 是随插件发布的唯一前端运行产物，包含 `remoteEntry.js`、暴露组件和依赖入口。

插件入口通过 `get_render_mode()` 返回 `("vue", "frontend/dist/assets")`。MoviePilot 从插件静态文件接口加载 `remoteEntry.js`，再挂载模块联邦暴露的 `Config` 组件。发布包包含 `frontend/dist/assets/`，不依赖源码和 `node_modules` 才能运行。

生产构建执行 `yarn build`，会清空并重建 `frontend/dist/`。测试模式只启用 Vue 编译，不启用模块联邦和构建产物清理插件，使组件测试直接覆盖源码。`yarn dev` 使用 Vite watch 持续生成生产形态的联邦产物。

本地插件仓通过 `PLUGIN_LOCAL_REPO_PATHS` 接入 MoviePilot，`PLUGIN_AUTO_RELOAD=true` 负责同步构建产物并热加载插件。`DEV=true` 只用于暂停定时任务，不承担源码或联邦产物同步。

### Host 契约

`Config` 只依赖 Host 提供的输入和事件，不直接持久化插件配置：

- `initialConfig`：Host 传入的动态配置；草稿层按稳定配置契约规范化。
- `api`：Host 注入的已认证 API 客户端，用于读取运行概况。
- `save`：提交包含全部稳定配置键的规范化 payload；一次性动作随本次保存提交并自动复位。
- `close`：请求 Host 直接关闭配置页，不在插件内部实现未保存修改确认。
- `layout`：请求 Host 使用 `68rem` 的配置页最大宽度。

桌面端“运行一次”提交 `onlyonce=true` 的完整保存 payload，保存成功后的关闭由 Host 统一处理。移动端保留表单内的一次性开关，并由保存动作提交。重置数据同样是保存触发的一次性命令。

### 前端测试架构

前端测试镜像源码责任域，但物理存放在仓库根测试目录，避免测试、fixture 和测试依赖进入插件运行时副本：

```text
tests/v2/subscribeassistantenhanced/frontend/
├── setup.ts
├── src/
│   ├── components/__tests__/Config.spec.ts
│   └── config/__tests__/*.spec.ts
└── support/
    ├── factories/config.ts
    ├── host.ts
    ├── msw/server.ts
    └── render.ts
```

- `setup.ts` 注册 jest-dom、浏览器观察器垫片、统一 cleanup 和 MSW 生命周期；未声明网络请求直接失败。
- `support/render.ts` 使用真实 Vue 与 Vuetify 挂载组件，只替换 Host 才提供的 CRON 和 YAML 编辑器，并注入 Host 语言契约。
- `support/host.ts` 提供 Host API 与运行概况测试替身。
- `support/factories/` 为每个用例创建独立的完整配置，避免共享可变状态。
- `src/config/__tests__/` 验证规范化、草稿、API、本地化和展示等纯逻辑契约。
- `Config.spec.ts` 只通过可见 DOM、accessible name、用户操作、emits、Host API 和挂载生命周期验证组件行为。
- Python 的 `test_vue_config_contract.py` 负责校验 Python Form 与 TypeScript 配置键、默认值和字段元数据的跨语言一致性。

Vitest 使用 jsdom、Testing Library、Vue Test Utils、MSW 和 V8 coverage。全局覆盖率门槛为分支 80%、函数 85%、行和语句 85%；纳入覆盖率的每个核心文件至少达到分支 75%、函数、行和语句 80%。`Config.vue` 的样式、容器查询、hover/focus、桌面与移动布局、联邦远程加载和 Host 保存关闭流程由真实 Chrome 验证。

前端 CI 仅在 SAE 前端源码、前端测试或工作流变化时运行，使用 Node 24 依次执行 frozen lockfile 安装、`yarn typecheck`、`yarn test:coverage` 和生产构建，并校验提交的 `dist/` 与源码构建结果一致。

## 入口层

入口层包含：

- 事件入口：订阅新增、订阅修改、订阅删除、下载新增、整理完成、插件命令。
- 链式事件入口：完成检查、集数刷新、资源选择、资源下载、整理拦截、数据重置。
- 定时任务入口：元数据巡检、待定释放、一致性检查、无下载检查、下载任务检查、洗版检查、完成校验、清理任务。
- 命令入口：用户通过插件命令触发的订阅操作。

入口层允许做：

- payload 校验和转换；
- 订阅、媒体信息、TMDB 分集等上下文读取；
- 非生命周期领域调用，例如优先级回填、识别增强、候选过滤、清理检查；
- 调用生命周期层执行订阅状态相关操作。

入口层不直接写 `state`，不直接组合暂停、待定、补搜、恢复保护和状态通知的顺序。

## 生命周期层

`SubscribeLifecycleCoordinator` 是订阅状态生命周期的统一编排层。凡是会影响以下事实的业务路径，都属于生命周期层职责：

- 主订阅状态：`N`、`R`、`P`、`S`。
- 暂停归属：`pause_reason`、`pause_since`、`pause_detail`。
- 待定归属：`pending_sources`、`source`、`reason`。
- 下载待定归属：`download_pending`。
- 状态变化派生副作用：补搜、状态通知、恢复保护、归属清理。

生命周期层不替代领域 writer。它负责决定跨领域顺序，并调用下游模块完成具体写入。

```mermaid
flowchart LR
    Context[入口上下文] --> Lifecycle[SubscribeLifecycleCoordinator]
    Lifecycle --> Decision{生命周期决策}
    Decision --> Pause[PauseManager]
    Decision --> Pending[PendingStateCoordinator]
    Decision --> Judge[PendingJudge]
    Decision --> Search[单订阅补搜]
    Decision --> Notify[状态通知]
    Decision --> Guard[恢复保护]
```

生命周期方法统一返回 `LifecycleResult`：

```python
@dataclass
class LifecycleResult:
    changed: bool = False
    stopped: bool = False
    state: str | None = None
    reason: str = ""
    message: str = ""
```

`changed` 表示状态或归属发生变化。`stopped` 表示入口后续生命周期流程应停止。`state`、`reason`、`message` 提供稳定的日志、命令回复和测试语义。

## 订阅状态模型

主程序订阅状态只表达用户可见状态：

- `N`：新增，仍处于主程序首次搜索窗口。
- `R`：启用，正常参与搜索与生命周期巡检。
- `P`：待定，存在至少一个插件持有的待定来源。
- `S`：禁用，存在用户、外部或插件持有的暂停事实。

插件归属状态解释 `P` 和 `S` 的原因。没有归属的 `P/S` 应被视为外部事实或残留事实，而不是默认归属于自动逻辑。

```mermaid
stateDiagram-v2
    [*] --> N
    N --> R: 主程序完成新增流程
    N --> P: pending_judge / guard_veto / download_pending
    N --> S: auto_user / pre_air / external
    R --> P: 任一待定来源进入
    R --> S: 暂停来源进入
    P --> R: 最后一个待定来源释放
    P --> S: 暂停覆盖待定
    S --> R: 插件持有暂停释放
    S --> S: external 归属保持
```

## 暂停领域

`PauseManager` 是暂停 writer。它维护：

- 暂停原因和详情；
- 暂停优先级；
- `S/R` 状态写入；
- 暂停和恢复通知去重；
- 恢复保护相关字段。

暂停原因采用优先级仲裁。`external` 代表用户或外部系统持有的暂停事实，并拥有最高优先级。`/subscribe_toggle` 产生的手动暂停也使用 `external`，通过 `pause_detail` 标明来源，例如“插件命令手动暂停”。

`AiringPauseChecker` 是暂停判定器。它根据上映日期、开播日期、下一集日期和完成证据返回 `PauseRecord` 或恢复判断，不写状态。

```mermaid
flowchart TD
    Media[媒体信息 + 分集 + 完成证据] --> Airing[AiringPauseChecker]
    Airing --> Record{PauseRecord?}
    Record -->|有| Lifecycle[Lifecycle]
    Lifecycle --> PauseManager[PauseManager]
    PauseManager --> Store[(pause_reason + state=S/R)]
```

## 待定领域

`PendingJudge` 负责 `pending_judge` 来源的待定判定。它根据开播窗口、集数、air_date 和完成证据判断是否应进入待定。

`PendingStateCoordinator` 是多来源待定 writer。它维护：

- `pending_sources`；
- 主来源 `source`；
- 当前原因 `reason`；
- `P/R` 状态同步；
- 暂停覆盖待定时的归属清理。

待定来源包括：

- `pending_judge`：剧集信息待确认。
- `guard_veto`：完成前检查未通过，需要观察。
- `download_pending`：下载已发起但尚未完成整理或下载器确认。

任一来源存在时订阅保持 `P`。只有最后一个来源释放后，订阅才恢复 `R`。

```mermaid
flowchart LR
    Judge[pending_judge] --> Sources[pending_sources]
    Guard[guard_veto] --> Sources
    Download[download_pending] --> Sources
    Sources --> State{是否还有来源?}
    State -->|有| P[state=P]
    State -->|无| R[state=R]
```

## 下载领域

`DownloadMonitor` 负责下载事实，不负责跨领域生命周期决策。它维护：

- 下载任务索引；
- hash 和无 hash 下载的临时匹配；
- 下载任务是否仍活跃；
- 下载待定过期判断。

下载事实可触发 `download_pending` 来源进入或释放，但该来源的生命周期归属由生命周期层协调，并最终由 `PendingStateCoordinator` 仲裁。

## 完成前观察

`CompletionGuard` 处理完成事件前的链式否决。它读取完成证据，判断是否应：

- 放行完成；
- 取消完成事件；
- 进入 `guard_veto` 待定观察；
- 记录或释放观察令牌。

完成前观察是待定来源之一，但不直接拥有待定状态写入。待定状态归属通过生命周期层进入 `PendingStateCoordinator`。

## 洗版领域

洗版领域包括：

- `BestVersionOrchestrator`：创建和编排洗版订阅。
- `BestVersionConverter`：分集洗版转全集洗版。
- `PriorityManager`：优先级回填和分集优先级维护。

洗版领域可以更新洗版相关字段、发送主程序事件和通知，但不拥有订阅生命周期状态。若洗版流程需要改变 `state` 或状态归属，应通过生命周期层。

## 清理领域

清理领域包括：

- `SubscriptionCleanup`：根据订阅完成、洗版完成和清理配置处理转移历史、旧媒体文件和旧记录。
- `TorrentCleanup`：处理旧种子删除、删除指纹、删种后补搜和下载待定清理。

清理领域处理资源和历史，不直接持有订阅生命周期状态。清理过程中如需释放 `download_pending` 或触发状态恢复，应通过生命周期层提供的接口。

## 识别与证据领域

识别和证据领域包括：

- `RecognitionGuard`：识别增强、候选准入和审计。
- `CompletionEvidencePipeline`：聚合 TMDB、站点证据、波动和本地完成事实。
- `SiteEvidence`：站点总集数和剧集证据。
- 完成快照与快照清理。

这些模块提供判定输入或诊断信息，不直接写 `state`、`pause_reason`、`pending_sources` 或 `download_pending`。

## 主要数据流

### 新增订阅

```mermaid
flowchart TD
    A[SubscribeAdded] --> B[EventProxy 读取订阅和媒体信息]
    B --> C[优先级回填]
    C --> L[Lifecycle]
    L --> U{用户名规则?}
    U -->|命中| S[写 auto_user 暂停]
    U -->|未命中| Pre{上映前暂停?}
    Pre -->|命中| P0[写 pre_air 暂停]
    Pre -->|未命中| Full{全集洗版?}
    Full -->|是| Done[结束生命周期处理]
    Full -->|否| Pending{剧集待定?}
    Pending -->|命中且 state=N| Search[安排单订阅补搜]
    Search --> P1[写 pending_judge 待定]
    Pending -->|命中且 state!=N| P1
    Pending -->|未命中| Gap{是否允许播出暂停?}
    Gap -->|允许| Airing[检查 airing_gap]
    Gap -->|不允许| Done
```

### 元数据巡检

```mermaid
flowchart TD
    A[run_meta_check] --> B[遍历 N/R/P/S]
    B --> L[Lifecycle]
    L --> Flag{标记暂停仍为 S?}
    Flag -->|是| Skip[跳过自动恢复]
    Flag -->|否| Media[识别媒体信息]
    Media --> PendingExit{P 态释放?}
    PendingExit -->|已释放| End[结束本订阅]
    PendingExit -->|未释放或非 P| Pause[暂停进入/刷新/恢复]
    Pause --> PendingEnter[待定进入判定]
    PendingEnter --> End
```

### 下载命中恢复暂停

```mermaid
flowchart TD
    A[DownloadAdded] --> Monitor[登记下载事实]
    Monitor --> L[Lifecycle]
    L --> Paused{state=S?}
    Paused -->|否| End[结束]
    Paused -->|是| Record{有 pause record?}
    Record -->|无| Adopt[登记 external 归属]
    Record -->|有| Resume[静默恢复]
    Adopt --> Resume
    Resume --> Guard{原因为 external?}
    Guard -->|否| ResumeGuard[写恢复保护]
    Guard -->|是| Notify[发送恢复通知]
    ResumeGuard --> Notify
```

## 允许的非生命周期更新

以下更新不属于生命周期状态：

- 洗版优先级和分集优先级。
- 转移历史、文件删除和种子删除。
- 识别增强审计和通知限频。
- 站点证据和完成快照。
- 底层 `shared.update.update_subscribe` 工具调用。

判断标准：不改变 `state=N/R/P/S`，不持有或释放 `pause_reason`，不持有或释放 `pending_sources`，不创建或释放 `download_pending`，也不触发状态变化派生的补搜、恢复保护或状态通知。

## 演进规则

- 新的入口如果改变订阅生命周期状态，必须接入生命周期层。
- 新的暂停原因、待定来源或下载待定来源，必须同步更新状态模型、生命周期测试和本文档图例。
- 入口层不得直接拼装多个生命周期副作用。
- 领域模块不得为了方便绕过生命周期层写状态归属。
- 测试应按入口、生命周期和领域 writer 分层维护；只验证调用路径、缺少业务断言的测试不应作为长期契约保留。
