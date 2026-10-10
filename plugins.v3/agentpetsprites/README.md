# 助手形象素材包

用精灵图和动作映射 JSON 定制 Agent 助手形象，内置放映猫素材包，可在配置页添加更多素材包。

> 兼容性：MoviePilot v3.x，需要主程序支持 Agent 助手形象扩展（`get_agent_pets`）；不支持的主程序会继续显示内置机器人
> 适用场景：已启用 MoviePilot Agent 助手，想用一套自己的逐帧形象替换右下角的机器人

## 版本更新日志

- v0.1.0
  - 新增 renderer 模式助手形象素材包，内置戴贝雷帽的橘猫「放映猫」
  - 配置页可以上传精灵图或填写图片 URL 添加素材包，按宿主动作与状态播放帧动画

## 功能概览

- 每个素材包在「助手形象」里显示为一个独立形象，预览图是素材包的 idle 帧
- 只替换助手入口的画面；拖拽、贴边、点击打开面板和气泡仍由主程序负责，行为和内置机器人一致
- 按主程序传来的动作名和状态播放帧序列，没有对应映射时依次回落到状态、思考中和 idle
- 主程序暂停动画（页面不活跃、系统减少动态效果）时只显示当前动作的第一帧
- 上传的精灵图保存在插件数据目录，按需经插件接口读取，不写进插件代码目录

## 命令 / API

| 类型 | 标识 | 说明 |
| --- | --- | --- |
| API | `GET /api/v1/plugin/AgentPetSprites/packs` | 素材包列表，登录用户可用 |
| API | `GET /api/v1/plugin/AgentPetSprites/pack?key=<id>` | 读取一个素材包及精灵图，登录用户可用 |
| API | `POST /api/v1/plugin/AgentPetSprites/packs` | 添加素材包，仅管理员 |
| API | `POST /api/v1/plugin/AgentPetSprites/packs/delete` | 删除素材包，仅管理员 |

## 配置说明

| 配置项 | 标识 | 类型 | 默认值 | 说明 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 启用插件 | `enabled` | bool | `false` | 启用后素材包出现在助手形象列表中 |  |

素材包不属于插件配置。在配置页「添加素材包」里校验通过后立即保存，删除也立即生效，无需再点保存。

## 素材包格式

一个素材包由一张精灵图和一份 JSON 组成。精灵图按网格等分，所有格子同尺寸，建议透明背景、角色脚底在同一基线上。

```json
{
  "id": "my-pet",
  "name": "我的形象",
  "description": "一句话介绍",
  "sheet": "https://example.com/my-pet.png",
  "grid": { "cols": 4, "rows": 2 },
  "frames": { "idle": 0, "blink": 1, "talk": 2, "think": 3, "jump": 4, "wave": 5, "sleep": 6, "sad": 7 },
  "actions": {
    "idle": { "frames": ["idle", "idle", "idle", "blink"], "frame_ms": 700, "loop": true },
    "thinking": { "frames": ["think"], "loop": true },
    "speaking": ["talk", "idle"],
    "success": { "frames": ["jump", "wave", "idle"], "frame_ms": 260 },
    "error": ["sad"],
    "wave": { "frames": ["wave", "idle", "wave"], "frame_ms": 240 },
    "sleep": ["sleep"]
  },
  "random_actions": ["wave", "sleep"]
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 否 | 素材包 ID，也是形象 key，只能用小写字母、数字、`-`、`_`，1 到 32 个字符；不填时按名称生成。`projector-cat` 留给内置素材包 |
| `name` | 是 | 展示名，不超过 40 个字符 |
| `description` | 否 | 一句话介绍，不超过 120 个字符 |
| `sheet` | 视添加方式 | 选择「使用 JSON 中的图片 URL」时必须是 `http(s)` 图片地址；上传精灵图时忽略 |
| `grid` | 是 | `cols`、`rows`，各 1 到 16；精灵图宽高必须能被行列数整除 |
| `frames` | 是 | 帧名到格子索引，索引从左上角 0 开始逐行编号；必须包含 `idle` |
| `actions` | 否 | 主程序动作名或状态名到帧序列，详见下文 |
| `random_actions` | 否 | 主程序空闲时随机播放的动作，只能取下文的主程序动作名；不填则从全部动作中挑 |
| `preview` | 否 | 自定义预览图，`http(s)` 地址或 `data:image/...`；上传方式不填时自动裁出 idle 帧 |

`actions` 的每一项写成对象 `{ "frames": [...], "frame_ms": 160, "loop": false }`，也可以直接写帧名列表，此时每帧 160 毫秒、不循环。`frame_ms` 范围 40 到 5000；不循环的动作播完停在最后一帧。

`actions` 的键可以是主程序动作名，也可以是状态名：

- 主程序动作名：`wave`、`sit`、`eye-roll`、`faint`、`disassemble`、`happy-jump`、`sleep`、`stretch`、`peek`、`scan`、`charge`、`spin-cheer`、`shy`、`confused`、`nod`、`wake`
- 状态名：`idle`、`thinking`、`speaking`、`notify`、`success`、`warning`、`error`、`dragging`、`docked`、`sleeping`、`reaction`

播放时先找当前动作名，找不到再找当前状态，助手正在思考时再试 `thinking`，最后用 `idle`。只给 `idle` 也能用，所有动作都会显示 idle。

精灵图支持 PNG、WebP、GIF 和 JPEG，不超过 4MB、边长不超过 4096 像素。一个实例最多保存 20 个素材包。

## 使用步骤

1. 在插件市场安装并启用「助手形象素材包」
2. 打开个人设置中的「助手形象」，选择「放映猫」；管理员也可以在系统设置中把它设为默认助手形象
3. 需要更多形象时，在配置页粘贴素材包 JSON，上传精灵图或改用 JSON 中的图片 URL，点击「校验并添加」
4. 新素材包会立即出现在「助手形象」列表里

插件详情页提供开发预览，按主程序入口的大小显示素材包，可以逐个切换动作、状态和事件检查帧映射。

## 注意事项 / 已知风险

- 删除素材包或停用插件后，选择它的用户会自动回到内置机器人
- 使用图片 URL 时，图片由每个用户的浏览器直接加载，地址失效或跨域受限时会显示空白；需要稳定显示时请上传精灵图

## 故障排查

- 主日志：`MoviePilot/config/logs/moviepilot.log`
- 插件日志：`MoviePilot/config/logs/plugins/`，过滤「助手形象素材包」
- 常见问题：
  - 「校验并添加」提示帧或动作错误 → 按提示检查 `frames` 索引是否超出 `cols × rows`，动作里的帧名是否都在 `frames` 中
  - 提示尺寸不能被网格整除 → 精灵图宽度必须是列数的整数倍，高度必须是行数的整数倍
  - 选择后显示的是放映猫 → 素材包读取失败时组件会退回内置素材包，浏览器控制台里会有 `[AgentPetSprites]` 警告
