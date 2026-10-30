# my-IPTV

[![Sync IPTV](https://github.com/hellomrli/my-IPTV/actions/workflows/sync-iptv.yml/badge.svg)](https://github.com/hellomrli/my-IPTV/actions/workflows/sync-iptv.yml)

个人 IPTV 播放列表维护仓库：定时同步上游广西移动 IPTV 列表，并保留本地 `IPTV.m3u` 的代理转发格式、分组、排序和频道图标。

> 仅供个人网络环境内测试使用。频道可用性取决于运营商网络、代理转发服务和上游列表状态。

## 功能特点

- 自动同步上游 `gx.m3u`，更新频道 ID / 播放地址。
- 保留本地 `#EXTINF` 元数据、分组和排序。
- 新增频道默认追加到列表末尾，也可关闭新增只更新现有频道。
- 同名频道按画质去重，优先级：`8K > 4K > 蓝光 > 极清 > 超清 > 高清 > 标清`。
- 默认排除测试、不可用或不想保留的频道，避免自动同步后反复出现。
- `icon/` 中保存频道台标，`IPTV.m3u` 使用 GitHub Raw 地址引用。
- 从同一份直播列表自动生成直连版、回放版，频道 ID 更新后回放地址同步更新。
- 延续 `test` 分支的历史 TS 寻址方案，提供节目回放及持续更新的时移 HLS 接口。

## 仓库结构

```text
.
├── IPTV.m3u                 # 对外使用的播放列表
├── IPTV-catchup.m3u         # 本地转发 + 回放属性（由脚本生成）
├── gx.m3u                   # 广西移动源站直连版（由脚本生成）
├── catchup.json             # 回放服务地址、播放器格式、频道保留窗口
├── icon/                    # 频道台标
├── scripts/
│   ├── sync_iptv.py         # 同步上游列表并保留本地格式
│   ├── build_playlists.py   # 从 IPTV.m3u 生成两个派生列表
│   ├── catchup_server.py    # 回放/时移 HLS 翻译服务
│   ├── diagnostics.py       # 有上限的请求统计与脱敏 JSON 日志
│   ├── upstream.py          # 带总截止时间的 HTTP(S) / DNS 访问
│   ├── openwrt_service.py   # 动态发布路由器订阅
│   ├── export_openwrt.py    # 导出可独立构建的 OpenWrt 源码包
│   └── update_icons.py      # 下载/更新频道台标并回写 tvg-logo
├── openwrt/                 # LuCI / procd 打包模板
├── tests/                   # 不依赖运营商网络的回归测试
└── .github/workflows/
    ├── check.yml            # 推送/PR 的离线检查
    └── sync-iptv.yml        # 每日同步、生成、测试
```

## 同步规则

| 项目 | 规则 |
|---|---|
| 上游来源 | `https://raw.githubusercontent.com/Healer-sys/Home/main/iptv/gx.m3u` |
| 本地转发格式 | 沿用模板里的 `http://192.168.50.250:8080/{频道ID}/index.m3u8?servicetype=1` |
| 已有频道 | 保留本地名称、分组、排序和图标，只替换频道 ID / URL |
| 新增频道 | 默认追加到末尾；使用 `--no-add-missing` 可关闭 |
| 去重策略 | 同名频道只保留画质最高的一条 |
| 排除策略 | 在 `scripts/sync_iptv.py` 的排除名单中维护 |

## 本地使用

在仓库目录中直接同步：

```bash
python3 scripts/sync_iptv.py
python3 scripts/build_playlists.py
```

使用外部模板并覆盖输出，同时保留备份：

```bash
python3 scripts/sync_iptv.py \
  --template /home/lain/下载/IPTV.m3u \
  --output /home/lain/下载/IPTV.m3u \
  --backup
```

只更新已有频道，不追加上游新增频道：

```bash
python3 scripts/sync_iptv.py --no-add-missing
```

更新台标：

```bash
python3 scripts/update_icons.py --playlist IPTV.m3u --icon-dir icon
```

## 自动更新

GitHub Actions 每天自动运行一次，也可以在 Actions 页面手动触发 `Sync IPTV`。

自动任务依次同步 `IPTV.m3u`、生成 `IPTV-catchup.m3u` / `gx.m3u`、执行离线测试；
仅在任一播放列表发生变化且测试通过时提交。推送和 PR 也会单独运行测试。

## 使用播放列表

GitHub Raw 地址格式：

```text
https://raw.githubusercontent.com/hellomrli/my-IPTV/main/IPTV.m3u
```

如果播放器无法访问 GitHub Raw，建议自行反代或下载到本地使用。

## 回放与时移

实现基于 `test` 分支的 `638e10f` 方案，不改变现有 `IPTV.m3u` 的直播地址。
`gx.m3u` 直接访问移动源站，仅适用于能路由到 ITV 网络的设备；
`IPTV-catchup.m3u` 仍走原来的直播代理，回放请求另行交给本服务。

### 启动与订阅

要求 Python **3.10+**，仅使用标准库，无需安装第三方依赖。在能访问直播代理的常开机器上运行：

```bash
python3 scripts/catchup_server.py 8081 http://192.168.50.250:8080
```

默认监听 `0.0.0.0:8081`；可用 `--host 127.0.0.1` 限制监听地址。
服务不录制、不缓存 TS 媒体；只保存有上限的锚点、短时地址/序号缓存和已观测断点。

**先修改 `catchup.json` 中的 `base_url` 为播放器可以访问的服务地址**
（默认沿用 test 分支的 `http://192.168.50.107:8081`），然后生成列表：

```bash
python3 scripts/build_playlists.py
```

在酷9中订阅 `IPTV-catchup.m3u`，通过已有 EPG 选择历史节目。默认保留 test 分支
针对酷9 2.2.21 使用的 `${(b)yyyyMMddHHmmss}` / `${(e)yyyyMMddHHmmss}` 格式。
其他播放器需按其支持的占位符选择生成格式，不能假定互通：

```bash
# 使用 Unix 秒占位符的客户端；该选项不会修改 catchup.json
python3 scripts/build_playlists.py --format unix --base-url http://192.168.50.107:8081
```

`unix` 输出 `{utc}` / `{utcend}`。需要长期保留此选项时，将配置中的 `format` 改为
`unix`，否则下次自动生成会恢复配置值。客户端应能同时访问回放服务和原直播代理；
TS 通过服务校验后 302 跳转到原代理，流量不经过 Python 服务。

### 接口及边界

| 接口 | 用途 |
|---|---|
| `/catchup/{频道ID}/{开始}/{结束}/index.m3u8` | 已结束节目输出 VOD；正在播出的节目持续追加，直到结束时间可用 |
| `/timeshift/{频道ID}/{开始}/index.m3u8` | 从指定历史时刻播放并持续更新，无固定结束时间 |
| `/status` | JSON 健康状态、缓存/断点数量、锚点年龄，以及请求耗时、探测统计和最近失败 |

- 14 位日期固定按北京时间 `UTC+08:00` 解释，与宿主机或容器时区无关；Unix 秒按 UTC。
- 回放第三段也兼容 `1..14400` 的时长秒；倒置日期、毫秒时间戳、超过 4 小时的回放返回 400，不再静默改写或截断。
- 起点必须在频道配置窗口内且至少落后当前时间 20 秒；直播锚点比当前时间更旧时，以锚点的可用完整片段为准。
- 时移的 HLS 窗口最多 4 小时，后续刷新会向前滑动；`EXT-X-START` 指向所请求的窗口起点。播放器是否提供暂停、拖动和“回到直播”按钮，由客户端决定，不是服务端接口本身的功能。
- 只允许 `catchup.json` 的频道名单。未知频道/找不到起始片段返回 404，超出窗口返回 416，上游错误/超时返回 502/504，繁忙时返回 503。
- 每次上游解析有 12 秒总截止时间，覆盖 DNS 等待、连接、HTTP(S) 响应头/响应体及跳转链；最多 4 个请求同时解析。即使上游持续缓慢发送字节，也会中止套接字读取并释放处理名额。系统 DNS 查询不可强行终止，因此最多保留 4 个后台查询，不会无限创建线程。
- 正常创建长播放列表不逐段探测。播放中的 TS 按需校验、搜索序号漂移并跳转；补齐 `±1..6` 的连续搜索，相邻分片优先使用已验证序号预测，失败再回退搜索，不把偏移盲目应用到其他频道或远处的历史时刻。
- 保存直播列表中按需观测到的 `EXT-X-DISCONTINUITY` 及序号/时间跳变，在相应片段前输出断点；时移窗口滑动时保持断点序号连续。**未被观测到的历史 PTS 重置仍无法仅凭直播锚点恢复**，不承诺修复所有源站重启或历史媒体损坏。已观测断点若不在生成列表的 10 秒网格上，会明确返回 502，不静默丢弃标记。
- 后续 TS 确实缺失时仍会返回 404；不会偷偷跳过 30 秒或伪造成功。断流、源站重启、保留期变化仍可能影响回放。

### 可回放频道

`catchup.json` 的 `days_by_channel` **沿用 test 分支测得的 79 个频道**：湖南卫视 7 天、
浙江卫视 4 天，其余 1 天。这是可配置上限，不是本次重新验证了所有频道/全部历史范围，
也不保证源站始终保留这么久；不在名单的频道不会被标记为可回放。

配置按本地频道名匹配，而不是 EPG 的 `tvg-id`：例如高清、4K 频道可能共用 EPG ID，
但回放可用性不同。改名时需同步更新配置。服务端按文件变化重新读取频道 ID 和配置，
无需因列表同步重启；服务地址、生成格式变更则需重新生成派生列表。

不要手工编辑派生的两个列表；修改 `IPTV.m3u` 或 `catchup.json` 后重新生成即可。
实现限制及修复记录见 [回放审查记录](docs/catchup-review.md)。

### 安全与部署

本服务没有认证，**仅限可信局域网，不要直接暴露到公网**。跨网访问应自行配置反代认证
或 VPN；反代时必须把 `/catchup/`、`/timeshift/`、`/segment/` 一起转发，并关闭播放列表缓存。
`base_url` 可以包含反代路径前缀，HLS 中的相对片段 URL 会保留这个前缀。

### 卡顿排障

`/status` 保留原有健康字段，并新增 `diagnostics`：累计请求及响应码、处理中请求数、
耗时、上游访问/分片探测次数、缓存命中与序号纠偏统计。失败请求与耗时达到 2 秒的慢请求
分别只保留最近 20 条，全部放在内存中，重启后清空，不写入路由器闪存。

GET / HEAD 响应附带服务端生成的 `X-Request-ID`，可以与诊断记录关联。
默认 `--access-log errors` 只向标准错误输出失败和慢请求的单行 JSON；临时排障可用
`--access-log all`，`--access-log off` 则关闭日志但保留内存统计。日志不保存完整 URL、
查询参数、客户端 IP、请求头或上游会话令牌，但仍含频道 ID 和节目时间，分享前请留意观看隐私。

这些指标只衡量 **Python 服务的请求处理与短探测**；302 不代表电视已收到或解码整个 TS，
不能用它断言已经找到卡顿原因。字段解释与采集步骤见 [排障指南](docs/diagnostics.md)。

### OpenWrt 源码包

当前打包模板版本为 `0.1.2-r1`，包含 LuCI 日志模式选项。模板不是完整安装包，
请先从仓库根目录导出到一个**不存在的新目录**，再运行包内测试：

```bash
python3 scripts/export_openwrt.py /tmp/luci-app-iptv-catchup-0.1.2
python3 /tmp/luci-app-iptv-catchup-0.1.2/tests/check.py
```

导出会注入运行脚本、频道数据、回归测试及 `SOURCE.json` 哈希清单。
APK / SDK 构建说明见 [OpenWrt 文档](openwrt/luci-app-iptv-catchup/README.md)；
源码版本更新不表示已构建、发布或部署 APK，**不要在观看中升级或修改服务配置**。

## 开发检查

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
```

离线测试覆盖时区独立性、时间边界、半小时/跨日/跨月目录、锚点相位、序号漂移、
空回放、动态时移、HTTP 错误及限流、派生列表一致性、频道 ID 更新等，不访问真实源站。
另有本机慢响应头、慢响应体、跳转链、受限 DNS 查询和 HTTPS 截止时间回归测试；
HTTPS 测试在有 `openssl` 命令时自动生成临时证书，没有该命令时跳过这两项，服务本身不依赖它。
导出回归测试检查 OpenWrt 包内源码哈希，并在隔离进程中导入运行模块，防止漏打包依赖。
诊断测试另覆盖并发计数、缓存/纠偏指标、失败原因、日志脱敏、HEAD / 连接复用及客户端写超时。
`Check IPTV` 工作流在 Python 3.10 / 3.14 上测试，并执行独立导出包测试及 LuCI / init 脚本语法检查。

## 注意事项

- 本仓库不包含账号、Cookie、密钥等敏感信息。
- 如需改变代理地址，请修改模板 playlist 中第一条可识别的频道 URL，脚本会沿用该 URL 格式替换频道 ID。
- 如果新增频道生成的 URL 不符合预期，请先确认模板 URL 中包含 `/{频道ID}/index.m3u8` 结构。
