# my-IPTV

同步上游广西移动 IPTV 列表，并保留本地 `IPTVnew.m3u` 的代理转发格式、分组和排序。

## 同步规则

- 上游来源：`https://github.com/Healer-sys/Home/blob/main/iptv/gx.m3u`
- 本地转发格式：沿用模板里的 `http://192.168.50.250:8080/{频道ID}/index.m3u8?servicetype=1`
- 已有频道：保留本地 `#EXTINF`、分组和排序，只更新频道 ID / 播放地址
- 上游新增频道：追加到列表末尾
- 同名频道去重：只保留画质最高的一条，优先级为 `8K > 4K > 蓝光 > 极清 > 超清 > 高清 > 标清`

## 本地使用

```bash
python3 scripts/sync_iptv.py \
  --template /home/lain/下载/IPTVnew.m3u \
  --output /home/lain/下载/IPTVnew.m3u \
  --backup
```

只更新已有频道、不追加上游新增频道：

```bash
python3 scripts/sync_iptv.py --no-add-missing
```

## 自动更新

GitHub Actions 每天自动运行一次，也可以在 Actions 页面手动触发 `Sync IPTV`。
