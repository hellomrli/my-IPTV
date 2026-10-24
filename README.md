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

## 仓库结构

```text
.
├── IPTV.m3u                 # 对外使用的播放列表
├── icon/                    # 频道台标
├── scripts/
│   ├── sync_iptv.py         # 同步上游列表并保留本地格式
│   └── update_icons.py      # 下载/更新频道台标并回写 tvg-logo
└── .github/workflows/
    └── sync-iptv.yml        # 每日自动同步
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

自动任务只会在 `IPTV.m3u` 发生变化时提交，避免无意义提交。

## 使用播放列表

GitHub Raw 地址格式：

```text
https://raw.githubusercontent.com/hellomrli/my-IPTV/main/IPTV.m3u
```

如果播放器无法访问 GitHub Raw，建议自行反代或下载到本地使用。

## 开发检查

```bash
python3 -m py_compile scripts/sync_iptv.py scripts/update_icons.py
```

## 注意事项

- 本仓库不包含账号、Cookie、密钥等敏感信息。
- 如需改变代理地址，请修改模板 playlist 中第一条可识别的频道 URL，脚本会沿用该 URL 格式替换频道 ID。
- 如果新增频道生成的 URL 不符合预期，请先确认模板 URL 中包含 `/{频道ID}/index.m3u8` 结构。

## test 分支: 回看(catchup)支持

本分支新增两个播放列表与一个回看翻译服务, 用于测试服务端回看:

- `gx.m3u` — 移动源直连地址版: 频道流地址直接指向广西移动 ITV 源站
  `cdnrrs.gx.chinamobile.com`(上游 `PLTV/77777777/224/{频道ID}` 格式),
  不经过本地 `192.168.50.250:8080` 转发, 仅在能路由到 ITV 网络的设备上可用。
- `IPTV-catchup.m3u` — 本地转发+回看版: 走 `192.168.50.250:8080` 转发,
  并给实测有服务端回看存储的 79 个频道追加了
  `catchup` / `catchup-days` / `catchup-source` 属性, 指向局域网回看翻译服务。
- `scripts/catchup_server.py` — 回看翻译服务。广西移动 ITV 网关不提供 playseek
  接口, 但历史 TS 片段按 `{unix时间戳}-1-{序号}.hls.ts` 规律可寻址; 本服务把
  `catchup-source` 里的时间参数翻译成实际存在的片段并合成 HLS VOD 播放列表。

运行方式(在局域网内任一常开机器上):

```bash
python3 scripts/catchup_server.py 8081 http://192.168.50.250:8080
```

播放器(酷9/TVBox 系)订阅 `IPTV-catchup.m3u` 后, 对这 79 个频道即可按节目单
回看(湖南卫视约 7 天、浙江卫视约 4 天、其余约 1 天)。注意: 网关对历史片段
的开放程度会波动(疑似存在限流保护), 短时 404 属正常, 服务内置了探测容错。
