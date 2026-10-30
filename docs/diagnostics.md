# 回放与时移排障

本功能用于区分“回放服务解析慢、找不到片段、上游访问失败”和服务已快速返回 302 的情况。
它不录制媒体、不转发 TS、不主动扫描频道，也不能测量电视实际下载或解码的耗时。
只在可信局域网使用；修改已有服务的配置、日志模式或版本前，请先避开观看时间。

## 采集方式

先读取运行中服务的状态，不会触发上游探测：

```bash
curl -fsS http://192.168.50.250:8088/status
```

默认模式 `errors` 输出失败和耗时达到 2 秒的请求。需要查看每次成功解析的纠偏及缓存信息时，
可以在独立端口启动临时实例，仅监听本机，不停止原服务：

```bash
python3 scripts/catchup_server.py 18081 http://192.168.50.250:8080 \
  --host 127.0.0.1 --access-log all 2>/tmp/iptv-catchup-access.jsonl
```

此实例供本机工具访问；需要电视对照测试时，改为指定可信 LAN 地址，并使用独立的测试订阅。
不要覆盖正在使用的订阅或把服务暴露到公网。排障完成后关闭临时实例；日志文件由使用者管理，
全量日志长期重定向到文件时需自行轮转。服务本身不创建日志文件。

OpenWrt 在 **服务 → IPTV 回放与时移 → 诊断日志** 中选择模式；保存并应用会重启服务，
之前的内存统计会清空，因此应在复现问题前、无人观看时配置。之后读取日志：

```sh
logread | grep 'iptv_request'
```

UCI 对应 `iptv-catchup.main.access_log`，可取 `errors`、`all`、`off`；旧配置没有此选项时默认
`errors`。`off` 只关闭请求日志，仍维护 `/status` 统计。成功请求默认不逐片刷日志。

## 状态字段

`/status` 顶层的 `status`、`cached_targets`、`sequence_hints`、`known_discontinuities`、
`anchors` 保持不变，新增 `diagnostics` 对象：

| 字段 | 含义 |
| --- | --- |
| `uptime_seconds` / `access_log` | 当前实例运行秒数、启用的日志模式 |
| `in_flight` | 尚未完成的 GET / HEAD 请求，包含当前读取 `/status` 的请求，不等于正在访问上游的数量 |
| `completed_requests` / `responses` / `endpoints` | 已完成请求数、响应码计数、固定接口类别计数；包含健康检查 |
| `failed_requests` / `client_disconnects` | HTTP 4xx / 5xx 或响应写入失败的请求数、其中客户端断连/写超时数 |
| `latency_ms` / `slow_requests` | 自启动以来完成请求的平均/最大处理耗时、耗时至少 2000 毫秒的请求数 |
| `resolution` | 已完成请求的上游访问、探测、缓存及纠偏累计计数 |
| `recent_errors` / `recent_slow_requests` | 最近失败和慢请求，各最多 20 条；同一请求可能同时出现在两者中 |

当前状态请求完成后才会加入累计计数。请求类别固定，不按客户端、完整 URL 或频道创建无限增长的
统计表。内存记录和计数随进程重启清空；读取状态不清空记录。尚未进入 GET / HEAD 处理函数的
HTTP 协议解析错误及不支持的方法不计入这些统计，因此它不是完整的 HTTP 审计日志。

## 单次请求

每条 JSON 记录包含 `event: "iptv_request"`、服务端生成的 `request_id`、UTC 请求时间、
方法、接口类别、响应状态码及 `duration_ms`。GET / HEAD 响应的 `X-Request-ID` 与之对应；
连接复用时每次请求仍会生成新 ID，不使用客户端传来的同名请求头。

有效的频道路径会记录 `channel`；能解析的节目/分片时间记录为 `media_start` / `media_end`
（Unix 秒）。`error` 是固定原因代码，不保存任意异常文本。上游 HTTP 错误另有 `upstream_status`。
`client_disconnected: true` 表示写响应失败，即使 `status` 是 200 / 302，也不能认定客户端收到了响应。

每条记录的 `resolution` 字段：

| 字段 | 含义 |
| --- | --- |
| `upstream_requests` / `upstream_ms` | 上游访问次数及累计耗时，覆盖读取响应体和失败路径；一次内部跳转链按一次访问计，不是线上 HTTP 报文总数 |
| `segment_probes` | 候选 TS 的短 Range 探测次数，不是完整下载次数 |
| `anchor_cache_hits` / `target_cache_hits` | 直播锚点缓存 / 已解析目标地址缓存命中次数 |
| `sequence_hint_hits` | 使用相同或相邻媒体时间的序号提示，并经探测验证成功的次数 |
| `sequence_corrections` | 返回的实际序号不同于请求预测序号的次数，含复用已经纠偏的目标缓存 |
| `sequence_offset` | 此请求最后一次成功解析的“实际序号减预测序号”；未解析成功时为 null，不跨请求累加 |

`duration_ms` 从进入处理函数计至响应写入结束或失败；`upstream_ms` 是访问上下文内的累计时间，
也包含其中少量本地解析工作。二者都不是 TS 下载速度或电视播放延迟。状态中的 `resolution`
只累加计数和访问时间，不累加 `sequence_offset`。

## 常见原因

| `error` | 检查方向 |
| --- | --- |
| `segment_missing` | 有限序号搜索后仍无可用历史片段；不意味着整个频道永久不可回放 |
| `stale_anchor` | 多次读取的直播列表仍过旧，检查网关缓存与直播源 |
| `invalid_ts` / `invalid_hls` / `unsupported_segments` / `encrypted_media` | 上游数据不符合当前服务支持的媒体格式 |
| `timestamp_phase_changed` | 已观测到的时间戳相位变化无法由固定 10 秒网格重建 |
| `upstream_http` | 查看 `upstream_status`，例如上游 429 限流或 5xx |
| `upstream_timeout` / `budget_exhausted` | 上游访问超时或耗尽整次解析预算；没有据此细分 DNS、TLS 或响应体阶段 |
| `upstream_connection` | 非超时的连接/解析错误，返回 502；超时返回 504 |
| `channel_disabled` / `outside_retention` / `live_edge` | 请求频道未启用、时间超出配置保留窗口或过于接近直播 |
| `invalid_time` / `invalid_path` / `not_found` | 请求时间格式、路径或接口不正确 |
| `busy` | 四个上游解析名额均被占用，返回 503 和 `Retry-After: 2` |
| `invalid_upstream_or_config` | 上游读取/解析或本地频道配置错误，需结合配置检查；该代码不进一步猜测根因 |

少量边界情况下还会出现 `invalid_anchor`、`playlist_too_large`；`service_error` 是扩展代码未指定原因时的兜底值。

如果耗时、探测次数持续很低且服务已返回 302，只能说明这段解析较快，仍需网关和播放器信息来
检查后续传输、缺片或解码。分享记录前注意：虽然没有完整 URL、查询参数、客户端 IP、请求头和
上游会话令牌，频道 ID 与节目时间仍可能透露观看习惯。不要上传包含敏感参数的原始订阅或网关日志。
