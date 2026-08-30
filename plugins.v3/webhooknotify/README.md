# Webhook消息推送

接收 Webhook 消息并推送到通知客户端。

> 兼容性：MoviePilot v3.x（最低版本：v3.0.0）
> 适用场景：路由、服务器、服务进程或其他外部监控系统的告警通知

## 版本更新日志

- v2.0.0
  - 迁移至 MoviePilot V3 稳定接口，保持 Webhook 请求与通知转发行为。
- v1.1
  - 新增 APIKEY 认证配置。
- v1.0
  - 新增通用 Webhook 通知入口。

## 功能概览

- 提供支持独立 API Key 的 `GET` 和 `POST` Webhook，避免向外部系统提供 MoviePilot 公共 `API_TOKEN`。
- 接收外部请求中的 `title` 和 `body`，任意一项非空即可转发为所配置类型的消息。
- 支持选择 MoviePilot 消息类型，默认为“插件”，用于匹配通知渠道的接收设置。
- 复用 MoviePilot 通知历史和已配置的 WebPush、Telegram、微信等通知渠道。
- 不负责健康检查、故障判断、重试或告警去重，调用方只负责在需要通知时发送请求。

## API

| 方法 | 地址 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/plugin/WebhookNotify/webhook` | 从 JSON 请求体接收入站通知 |
| `GET` | `/api/v1/plugin/WebhookNotify/webhook?title=...&body=...` | 从查询参数接收入站通知 |

认证信息支持以下任一传递方式：

- 请求头：`X-API-KEY: <API_KEY>`
- 查询参数：`?apikey=<API_KEY>`

配置“APIKEY”后，`API_KEY` 必须使用插件中配置的 Key；留空时使用 MoviePilot 公共 `API_TOKEN`。两种模式使用相同的请求头和查询参数名称。

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
  "https://moviepilot.example.com/api/v1/plugin/WebhookNotify/webhook" \
  -H "X-API-KEY: WEBHOOK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title":"路由故障","body":"主线路连续 3 次探测失败"}'
```

仅发送正文的 `GET` 示例：

```bash
curl --get \
  "https://moviepilot.example.com/api/v1/plugin/WebhookNotify/webhook" \
  --data-urlencode "apikey=WEBHOOK_API_KEY" \
  --data-urlencode "body=主线路连续 3 次探测失败"
```

## 配置说明

| 配置项 | 标识 | 类型 | 默认值 | 说明 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 启用插件 | `enabled` | bool | `false` | 是否接收入站 Webhook | 停用时接口返回 `503` |
| [消息类型](#cfg-notify_type) | `notify_type` | enum | `Plugin`（插件） | 设置通知分类和渠道过滤类型 | 调用方不能通过 Webhook 覆盖 |
| [APIKEY](#cfg-api_key) | `api_key` | string | 空 | 设置 Webhook 专用凭据 | 留空时使用主程序公共 `API_TOKEN` |

## 深入说明

<a id="cfg-notify_type"></a>
#### 消息类型（`notify_type`）

MoviePilot 的通知渠道可分别选择接收哪些消息类型。Webhook 消息会使用这里选择的类型进入通知链，只有允许该类型的渠道才会向客户端推送；该配置不改变标题或正文内容。

可选值为：`Download`（资源下载）、`Organize`（整理入库）、`Subscribe`（订阅）、`SiteMessage`（站点）、`MediaServer`（媒体服务器）、`Manual`（手动处理）、`Plugin`（插件）、`Agent`（智能体）和 `Other`（其它）。默认使用 `Plugin`（插件）；配置缺失或不是有效枚举值时同样按“插件”处理。

<a id="cfg-api_key"></a>
#### APIKEY（`api_key`）

配置后，Webhook 只接受该独立 Key，不再接受 MoviePilot 公共 `API_TOKEN`。外部监控系统仍通过 `X-API-KEY` 请求头或 `apikey` 查询参数传递凭据。留空时由主程序使用同样的入口校验公共 `API_TOKEN`。

建议使用足够长的随机字符串，并优先通过 `X-API-KEY` 请求头传递，避免查询参数被反向代理访问日志记录。独立 Key 泄露后只需在插件配置中轮换，不影响 MoviePilot 的其他公共 API。

## 使用步骤

1. 在插件市场安装并启用 Webhook消息推送。
2. 选择消息类型，并确认 MoviePilot 中至少有一个已启用通知渠道允许接收该类型。
3. 建议配置 APIKEY，并在调用方中通过 `X-API-KEY` 请求头传递；未配置时使用 MoviePilot 公共 `API_TOKEN`。
4. 使用 `GET` 查询参数或 `POST` JSON 发送通知，`title` 和 `body` 至少提供一项，确认客户端收到通知。

## 注意事项 / 已知风险

- 独立 API Key 和公共 `API_TOKEN` 都属于敏感凭据，请通过 HTTPS 传输；优先使用请求头，避免凭据进入 URL 日志。
- 插件只负责提交通知，不会为重复请求做去重；健康监测的失败阈值、恢复判定和重试策略由调用方负责。
- 消息是否实际发送仍受 MoviePilot 通知渠道配置和所选消息类型开关影响。

## 故障排查

- 插件请求日志位于 `/config/logs/plugins/webhooknotify.log`，记录请求方式、消息类型以及标题、正文是否存在，不记录 API Key 或消息内容。
- 返回 `401`：已配置独立 API Key 时检查插件 Key；未配置时检查 MoviePilot 公共 `API_TOKEN`。凭据应通过 `X-API-KEY` 或 `apikey` 传递。
- 返回 `422`：检查参数长度、JSON 格式，并确认 `title`、`body` 至少有一项为非空字符串。
- 返回 `503`：插件在 WebUI 中处于停用状态。
- 接口返回成功但客户端无消息：检查通知渠道是否启用，以及是否允许接收插件配置的消息类型。
