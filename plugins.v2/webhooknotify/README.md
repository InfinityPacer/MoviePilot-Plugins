# Webhook消息推送

接收 Webhook 消息并推送到通知客户端。

> 兼容性：MoviePilot v2.x
> 适用场景：路由、服务器、服务进程或其他外部监控系统的告警通知

## 版本更新日志

- v1.0
  - 新增通用 Webhook 通知入口，支持 GET、POST 和消息类型配置。

## 功能概览

- 提供受 MoviePilot 公共 `API_TOKEN` 保护的 `GET` 和 `POST` Webhook。
- 接收外部请求中的 `title` 和 `body`，任意一项非空即可转发为所配置类型的消息。
- 支持选择 MoviePilot 消息类型，默认为“插件”，用于匹配通知渠道的接收设置。
- 复用 MoviePilot 通知历史和已配置的 WebPush、Telegram、微信等通知渠道。
- 不负责健康检查、故障判断、重试或告警去重，调用方只负责在需要通知时发送请求。

## API

| 方法 | 地址 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/plugin/WebhookNotify/webhook?token=API_TOKEN` | 从 JSON 请求体接收入站通知 |
| `GET` | `/api/v1/plugin/WebhookNotify/webhook?token=API_TOKEN&title=...&body=...` | 从查询参数接收入站通知 |

`POST` 请求头使用 `Content-Type: application/json`，请求体格式如下：

```json
{
  "title": "路由故障",
  "body": "主线路连续 3 次探测失败"
}
```

`title` 和 `body` 均为可选字段，但至少需要提供一项非空内容；`title` 最长 200 个字符，`body` 最长 10000 个字符。`GET` 请求使用同名查询参数。接口成功接收后返回：

```json
{
  "success": true,
  "message": "通知已提交",
  "data": {}
}
```

`POST` 示例：

```bash
curl -X POST \
  "https://moviepilot.example.com/api/v1/plugin/WebhookNotify/webhook?token=API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"路由故障","body":"主线路连续 3 次探测失败"}'
```

仅发送正文的 `GET` 示例：

```bash
curl --get \
  "https://moviepilot.example.com/api/v1/plugin/WebhookNotify/webhook" \
  --data-urlencode "token=API_TOKEN" \
  --data-urlencode "body=主线路连续 3 次探测失败"
```

## 配置说明

| 配置项 | 标识 | 类型 | 默认值 | 说明 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 启用插件 | `enabled` | bool | `false` | 是否接收入站 Webhook | 使用主程序公共 `API_TOKEN`，无需重复配置 |
| [消息类型](#cfg-notify_type) | `notify_type` | enum | `Plugin`（插件） | 设置通知分类和渠道过滤类型 | 调用方不能通过 Webhook 覆盖 |

## 深入说明

<a id="cfg-notify_type"></a>
#### 消息类型（`notify_type`）

MoviePilot 的通知渠道可分别选择接收哪些消息类型。Webhook 消息会使用这里选择的类型进入通知链，只有允许该类型的渠道才会向客户端推送；该配置不改变标题或正文内容。

可选值为：`Download`（资源下载）、`Organize`（整理入库）、`Subscribe`（订阅）、`SiteMessage`（站点）、`MediaServer`（媒体服务器）、`Manual`（手动处理）、`Plugin`（插件）、`Agent`（智能体）和 `Other`（其它）。默认使用 `Plugin`（插件）；配置缺失或不是有效枚举值时同样按“插件”处理。

## 使用步骤

1. 在插件市场安装并启用 Webhook消息推送。
2. 选择消息类型，并确认 MoviePilot 中至少有一个已启用通知渠道允许接收该类型。
3. 将调用方的 Webhook 地址配置为插件 API 地址，将 `API_TOKEN` 放在 `token` 查询参数中。
4. 使用 `GET` 查询参数或 `POST` JSON 发送通知，`title` 和 `body` 至少提供一项，确认客户端收到通知。

## 注意事项 / 已知风险

- `API_TOKEN` 具备 MoviePilot 公共集成权限，请只在受信任的监控系统中使用，并通过 HTTPS 传输。
- 插件只负责提交通知，不会为重复请求做去重；健康监测的失败阈值、恢复判定和重试策略由调用方负责。
- 消息是否实际发送仍受 MoviePilot 通知渠道配置和所选消息类型开关影响。

## 故障排查

- 插件请求日志位于 `/config/logs/plugins/webhooknotify.log`，记录请求方式、消息类型以及标题、正文是否存在，不记录 `API_TOKEN` 或消息内容。
- 返回 `401`：检查 URL 中的 `token` 是否为当前 MoviePilot 公共 `API_TOKEN`。
- 返回 `422`：检查参数长度、JSON 格式，并确认 `title`、`body` 至少有一项为非空字符串。
- 返回 `503`：插件在 WebUI 中处于停用状态。
- 接口返回成功但客户端无消息：检查通知渠道是否启用，以及是否允许接收插件配置的消息类型。
