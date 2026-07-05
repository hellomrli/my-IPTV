#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen


RAW_BASE = "https://raw.githubusercontent.com/hellomrli/my-IPTV/main/icon"
USER_AGENT = "my-IPTV-icon-sync/1.0"
LOGO_RE = re.compile(r'tvg-logo="([^"]*)"')

REFERENCE_TREES = (
    ("taksssss", "https://api.github.com/repos/taksssss/tv/contents/icon"),
    ("fanmingming", "https://api.github.com/repos/fanmingming/live/git/trees/main?recursive=1"),
    ("ccsh", "https://api.github.com/repos/CCSH/IPTV/git/trees/main?recursive=1"),
)

MANUAL_ICON_URLS = {
    "北京纪实": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/BRTV北京纪实.png",
    "黑莓电影": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV黑莓电影.png",
    "黑莓动画": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV黑莓动画.png",
    "哒啵赛事": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV哒啵赛事.png",
    "哒啵电竞": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV哒啵电竞.png",
    "精品萌宠": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV精品萌宠.png",
    "动作电影": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV动作电影.png",
    "热播精选": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV热播精选.png",
    "爱情喜剧": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV爱情喜剧.png",
    "精品大剧": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV精品大剧.png",
    "中国功夫": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV中国功夫.png",
    "军事评论": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV军事评论.png",
    "农业致富": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV农业致富.png",
    "怡伴健康": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV怡伴健康.png",
    "精品体育": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV精品体育.png",
    "炫舞未来": "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/NEWTV炫舞未来.png",
    "来宾电视台综合": "https://raw.githubusercontent.com/CCSH/IPTV/main/logo/来宾综合.png",
    "钦州新闻综合": "https://raw.githubusercontent.com/CCSH/IPTV/main/logo/钦州新闻综合高清.png",
    "珠江卫视": "https://raw.githubusercontent.com/fanmingming/live/main/tv/广东珠江.png",
}


def request_json(url: str):
    url = encode_url(url)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def request_bytes(url: str) -> tuple[bytes, str]:
    url = encode_url(url)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=8) as response:
        content_type = response.headers.get("content-type", "")
        return response.read(), content_type


def encode_url(url: str) -> str:
    parts = urlsplit(url)
    path = quote(parts.path, safe="/%+")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def channel_name(extinf: str) -> str:
    return extinf.rsplit(",", 1)[-1].strip()


def current_logo(extinf: str) -> str | None:
    match = LOGO_RE.search(extinf)
    return match.group(1).strip() if match and match.group(1).strip() else None


def safe_filename(name: str, extension: str = ".png") -> str:
    value = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return f"{value}{extension}"


def public_icon_url(filename: str) -> str:
    return f"{RAW_BASE}/{quote(filename)}"


def set_logo(extinf: str, logo_url: str) -> str:
    if LOGO_RE.search(extinf):
        return LOGO_RE.sub(f'tvg-logo="{logo_url}"', extinf, count=1)
    return extinf.replace("#EXTINF:-1", f'#EXTINF:-1 tvg-logo="{logo_url}"', 1)


def parse_entries(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    pending_extinf: str | None = None
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            pending_extinf = line
            continue
        if pending_extinf and not line.startswith("#"):
            entries.append((pending_extinf, line))
            pending_extinf = None
    return entries


def load_reference_icons() -> dict[str, list[str]]:
    icons: dict[str, list[str]] = {}

    for source, url in REFERENCE_TREES:
        try:
            data = request_json(url)
        except Exception as exc:
            print(f"warning: failed to load {source} icon index: {exc}", file=sys.stderr)
            continue

        if source == "taksssss":
            for item in data:
                name = item.get("name", "")
                if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    continue
                channel = Path(name).stem
                icons.setdefault(channel, []).append(
                    f"https://gcore.jsdelivr.net/gh/taksssss/tv/icon/{quote(name)}"
                )
            continue

        for item in data.get("tree", []):
            path = item.get("path", "")
            if item.get("type") != "blob" or not path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            if source == "fanmingming" and not path.startswith("tv/"):
                continue
            if source == "ccsh" and not path.startswith("logo/"):
                continue
            channel = Path(path).stem
            repo = "fanmingming/live" if source == "fanmingming" else "CCSH/IPTV"
            icons.setdefault(channel, []).append(f"https://raw.githubusercontent.com/{repo}/main/{quote(path)}")

    return icons


def candidate_urls(name: str, existing_logo: str | None, references: dict[str, list[str]]) -> list[str]:
    candidates: list[str] = []
    if name in MANUAL_ICON_URLS:
        candidates.append(MANUAL_ICON_URLS[name])
    candidates.extend(references.get(name, []))
    if name.endswith("台"):
        candidates.extend(references.get(name[:-1], []))
    if existing_logo:
        candidates.append(existing_logo)

    deduped: list[str] = []
    for url in candidates:
        if url and url not in deduped:
            deduped.append(url)
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser(description="Download channel logos into icon/ and rewrite IPTV.m3u logo URLs.")
    parser.add_argument("--playlist", default="IPTV.m3u", help="Playlist to update.")
    parser.add_argument("--icon-dir", default="icon", help="Directory for downloaded icons.")
    args = parser.parse_args()

    playlist_path = Path(args.playlist)
    icon_dir = Path(args.icon_dir)
    icon_dir.mkdir(parents=True, exist_ok=True)

    text = playlist_path.read_text(encoding="utf-8-sig")
    references = load_reference_icons()
    entries = parse_entries(text)

    replacements: dict[str, str] = {}
    missing: list[str] = []
    downloaded = 0

    for index, (extinf, _url) in enumerate(entries, start=1):
        name = channel_name(extinf)
        filename = safe_filename(name)
        target = icon_dir / filename
        print(f"[{index}/{len(entries)}] {name}", flush=True)

        if not target.exists():
            for logo_url in candidate_urls(name, current_logo(extinf), references):
                try:
                    body, content_type = request_bytes(logo_url)
                except Exception:
                    continue
                if not content_type.startswith("image/") and not body.startswith((b"\x89PNG", b"\xff\xd8", b"RIFF")):
                    continue
                target.write_bytes(body)
                downloaded += 1
                break

        if target.exists():
            replacements[extinf] = set_logo(extinf, public_icon_url(filename))
        else:
            missing.append(name)

    for old, new in replacements.items():
        text = text.replace(old, new, 1)

    playlist_path.write_text(text, encoding="utf-8", newline="\n")

    print(f"icons={len(replacements)}, downloaded={downloaded}, missing={len(missing)}")
    if missing:
        print("missing:")
        for name in missing:
            print(name)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
