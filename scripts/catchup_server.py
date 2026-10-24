#!/usr/bin/env python3
"""广西移动 ITV 回看翻译层。

网关(经 Lucky 反代)不提供 playseek / catchup 的 m3u8 接口, 但历史 TS 片段
按 "{unix时间戳}-1-{序号}.hls.ts" 的时间寻址方式保留在服务端(各频道
数小时到 7 天不等)。本服务把"频道 + 时间范围"翻译成这些片段组成的
标准 HLS VOD 播放列表, 供任何支持 catchup 的播放器回看。

用法:
    python3 catchup_server.py [端口=8081] [网关=http://192.168.50.250:8080]

接口:
    /catchup/{频道ID}/{utc起始}/{utc结束}/index.m3u8   (结束也可传时长秒)
    /status
"""
import re
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
GATEWAY = sys.argv[2] if len(sys.argv) > 2 else "http://192.168.50.250:8080"
SEG_DUR = 10            # 每个片段 10 秒
MAX_WINDOW = 4 * 3600   # 单次请求最大回看时长(播放列表太大探测会很久)
ANCHOR_TTL = 60         # 直播锚点缓存秒数
UA = "okhttp/3.12.0"

_anchors = {}  # cid -> (time, base, sess, unix, seq)

DRIFTS = [0, -6, 6, -12, 12, -18, 18, -30, 30, -60, 60,
          -120, 120, -240, 240, -480, 480, -960, 960]


def http_get(url, timeout=8, rng=None):
    headers = {"User-Agent": UA}
    if rng:
        headers["Range"] = rng
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp


def fetch_live(cid):
    """取直播播放列表, 得到转发基地址/会话/当前片段的 (unix, seq) 锚点。"""
    now = time.time()
    hit = _anchors.get(cid)
    if hit and now - hit[0] < ANCHOR_TTL:
        return hit[1], hit[2], hit[3], hit[4]
    # 带缓存戳请求并校验新鲜度: 锚点必须取列表里"最新"的一段,
    # 且距当前时刻过远(反代缓存住了旧列表)时重试。
    for attempt in range(3):
        bust = f"&_cb={int(time.time()*1000)}" if attempt else ""
        resp = http_get(f"{GATEWAY}/{cid}/index.m3u8?servicetype=1{bust}")
        final = resp.geturl()
        body = resp.read().decode("utf-8", "ignore")
        resp.close()
        pairs = re.findall(r"/(\d+)-1-(\d+)\.hls\.ts", body)
        if pairs and int(pairs[-1][0]) > time.time() - 180:
            break
    else:
        raise RuntimeError("stale live playlist (proxy cache?)")
    base = final.rsplit("/", 1)[0]
    m = re.search(r"IASHttpSessionId=[^&]+", final)
    sess = m.group(0) if m else ""
    rec = (now, base, sess, int(pairs[-1][0]), int(pairs[-1][1]))
    _anchors[cid] = rec
    return rec[1], rec[2], rec[3], rec[4]


def seg_url(base, sess, cid, unix, seq):
    pt = time.strftime("%Y%m%d%H%M%S", time.gmtime(unix))
    ym = time.strftime("%Y%m", time.gmtime(unix))
    bucket = time.strftime("%d%H", time.gmtime(unix)) + "30"
    return (f"{base}/1/{ym}/{bucket}/{unix}-1-{seq}.hls.ts"
            f"?zduration={SEG_DUR}&ts_min=1&prog_time={pt}&{sess}"
            f"&ispcode=1108&ztecid={cid}")


def probe(url):
    """片段是否存在: Range 请求只看状态码。"""
    try:
        resp = http_get(url, timeout=6, rng="bytes=0-0")
        code = resp.status
        resp.close()
        return code in (200, 206)
    except Exception:
        return False


def resolve_range(cid, start, end):
    """把 [start, end) 翻译成实际存在的片段列表。

    网关片段时间戳不与绝对 10 秒整对齐(存在相位差), 因此所有片段的
    (unix, seq) 一律从直播锚点按整段数回推, 不做独立的时间取整:
        n 段前 -> unix_a - n*10, seq_a - n
    序号与时间大体线性, 但存在漂移和空洞: 先在起点附近做漂移搜索,
    之后线性外推并抽样校验(每12段探一次), 抽检失败再局部重搜;
    完全找不到的 30 秒空洞直接跳过。
    """
    base, sess, unix_a, seq_a = fetch_live(cid)
    n0 = (unix_a - start) // SEG_DUR          # 起点所在段(不早于 start)
    n1 = (unix_a - end) // SEG_DUR            # 终点所在段
    drift = None
    segs = []
    n = n0
    i = 0
    while n > n1:
        unix, seq = unix_a - n * SEG_DUR, seq_a - n
        need_probe = drift is None or i % 12 == 0
        if need_probe:
            cands = DRIFTS if drift is None else [drift + d for d in (0, -6, 6, -12, 12, -30, 30)]
            hit = None
            for d in cands:
                if probe(seg_url(base, sess, cid, unix, seq + d)):
                    hit = d
                    break
            if hit is None:
                n -= 3                          # 空洞: 跳过 30 秒
                i += 3
                continue
            drift = hit
        segs.append((unix, seq + drift))
        n -= 1
        i += 1
    return base, sess, cid, segs


def build_playlist(base, sess, cid, segs):
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:10",
             "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for unix, seq in segs:
        pdt = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(unix))
        lines.append(f"#EXT-X-PROGRAM-DATE-TIME:{pdt}")
        lines.append(f"#EXTINF:{SEG_DUR}.0,")
        lines.append(seg_url(base, sess, cid, unix, seq))
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def parse_ts(v):
    v = v.strip()
    if len(v) == 14 and v.isdigit():          # YYYYMMDDHHMMSS 当地时间(北京时间)
        return int(time.mktime(time.strptime(v, "%Y%m%d%H%M%S"))) - 8 * 3600
    return int(v)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send_body(self, code, body, ctype="text/plain; charset=utf-8"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/status":
            info = {c: {"age": int(time.time() - a[0])} for c, a in _anchors.items()}
            self.send_body(200, repr(info))
            return
        m = re.match(r"^/catchup/(\d+)/([^/]+)/([^/]+)/index\.m3u8$", path)
        if not m:
            self.send_body(404, "usage: /catchup/{cid}/{utc_start}/{utc_end}/index.m3u8")
            return
        cid = m.group(1)
        try:
            a = parse_ts(m.group(2))
            b = parse_ts(m.group(3))
            if b <= a:                     # 第二个参数是时长(秒)
                b = a + b
        except Exception:
            self.send_body(400, "bad timestamps")
            return
        now = int(time.time())
        if a > now - 60:
            a = now - 60                   # 别从未来/直播边缘取
        if b - a > MAX_WINDOW:
            b = a + MAX_WINDOW
        if b <= a:
            self.send_body(400, "empty range")
            return
        try:
            playlist = build_playlist(*resolve_range(cid, a, b))
        except Exception as e:
            self.send_body(502, f"upstream error: {e}")
            return
        if len(playlist.splitlines()) <= 6:
            self.send_body(404, "no segments found for range")
            return
        self.send_body(200, playlist, "application/vnd.apple.mpegurl")


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"catchup server on :{PORT}, gateway {GATEWAY}", flush=True)
    srv.serve_forever()
