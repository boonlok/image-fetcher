"""
fetch_images.py - 输入物品清单,自动到网上搜图并下载到本地。

用法:
    python fetch_images.py                         # 读取同目录的 items.txt
    python fetch_images.py --items my_list.txt
    python fetch_images.py "excavator=5" "safety helmet=10"
    python fetch_images.py --count 8 --out downloads "concrete crusher"

items.txt 格式 (每行一个物品):
    挖掘机 | 5
    safety helmet, 10
    concrete crusher            # 没写数量就用 --count 的默认值
    # 井号开头的行会被忽略

搜索来源: DuckDuckGo 图片 (免费, 免 API key)。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # Windows 控制台默认不是 UTF-8
    except Exception:
        pass

try:
    from ddgs import DDGS
except ImportError:
    print("缺少依赖,请先运行:  pip install ddgs", file=sys.stderr)
    sys.exit(1)

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}
LINE_RE = re.compile(r"^(.*?)\s*[|,=]\s*(\d+)\s*$")


def parse_items(lines: list[str], default_count: int) -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if m:
            name, count = m.group(1).strip(), int(m.group(2))
        else:
            name, count = line, default_count
        if name:
            items.append((name, max(1, count)))
    return items


def safe_folder_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip().strip(".")
    return cleaned or "item"


def guess_ext(content_type: str, url: str, data: bytes) -> str:
    ct = (content_type or "").lower()
    mapping = {
        "jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "gif": ".gif",
        "webp": ".webp", "bmp": ".bmp", "svg": ".svg", "tiff": ".tif",
    }
    for key, ext in mapping.items():
        if key in ct:
            return ext
    path_ext = Path(urlparse(url).path).suffix.lower()
    if path_ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}:
        return ".jpg" if path_ext == ".jpeg" else path_ext
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def download_one(url: str, timeout: int, min_size: int) -> tuple[bytes, str] | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        resp.raise_for_status()
        data = resp.content
    except Exception:
        return None
    if len(data) < 2000:  # 太小,基本是占位图/图标
        return None
    ext = guess_ext(resp.headers.get("Content-Type", ""), url, data)
    if HAVE_PIL and ext != ".svg":
        try:
            im = Image.open(io.BytesIO(data))
            im.verify()
            im = Image.open(io.BytesIO(data))
            if min(im.size) < min_size:
                return None
        except Exception:
            return None
    return data, ext


def fetch_item(
    name: str,
    count: int,
    out_dir: Path,
    timeout: int,
    min_size: int,
    safesearch: str,
) -> dict:
    folder = out_dir / safe_folder_name(name)
    folder.mkdir(parents=True, exist_ok=True)

    want = count
    try:
        results = list(
            DDGS().images(name, max_results=max(want * 4, want + 8), safesearch=safesearch)
        )
    except Exception as e:
        print(f"  [!] 搜索失败 '{name}': {e}")
        return {"name": name, "requested": count, "saved": [], "folder": folder}

    seen_hashes: set[str] = set()
    saved: list[Path] = []
    idx = 1

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(download_one, r.get("image"), timeout, min_size): r.get("image")
            for r in results
            if r.get("image")
        }
        for fut in as_completed(futures):
            if len(saved) >= want:
                break
            res = fut.result()
            if not res:
                continue
            data, ext = res
            h = hashlib.md5(data).hexdigest()
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            path = folder / f"{idx:03d}{ext}"
            try:
                path.write_bytes(data)
                saved.append(path)
                idx += 1
            except Exception:
                continue

    status = "OK" if len(saved) >= want else f"只找到 {len(saved)}/{want}"
    print(f"  {name}: {len(saved)} 张  [{status}]  -> {folder}")
    return {"name": name, "requested": count, "saved": saved, "folder": folder}


def write_summary(results: list[dict], out_dir: Path) -> Path:
    rows = []
    total = 0
    for r in results:
        total += len(r["saved"])
        thumbs = "".join(
            f'<a href="{p.relative_to(out_dir).as_posix()}" target="_blank">'
            f'<img src="{p.relative_to(out_dir).as_posix()}" loading="lazy"></a>'
            for p in r["saved"]
        )
        rows.append(
            f'<section><h2>{r["name"]} '
            f'<span class="q">需求数量: {r["requested"]}</span> '
            f'<span class="c">已下载: {len(r["saved"])} 张</span></h2>'
            f'<div class="grid">{thumbs or "<p>没有找到图片</p>"}</div></section>'
        )
    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>图片下载汇总</title><style>
body{{font-family:system-ui,"Microsoft YaHei",sans-serif;margin:0;padding:24px;background:#f6f6f7;color:#1a1a1a}}
h1{{margin:0 0 4px}} .meta{{color:#666;margin-bottom:24px}}
section{{background:#fff;border:1px solid #e3e3e5;border-radius:12px;padding:16px 20px;margin-bottom:18px}}
h2{{font-size:17px;margin:0 0 12px;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}}
.q{{font-size:13px;font-weight:600;color:#0a58ca;background:#e7f0ff;padding:2px 8px;border-radius:999px}}
.c{{font-size:13px;font-weight:500;color:#555;background:#eee;padding:2px 8px;border-radius:999px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}}
.grid img{{width:100%;height:150px;object-fit:cover;border-radius:8px;border:1px solid #ddd;background:#fafafa}}
</style></head><body>
<h1>图片下载汇总</h1>
<div class="meta">生成时间 {time.strftime("%Y-%m-%d %H:%M")} &nbsp;|&nbsp; 物品 {len(results)} 种 &nbsp;|&nbsp; 图片共 {total} 张</div>
{"".join(rows)}
</body></html>"""
    path = out_dir / "summary.html"
    path.write_text(html, encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="输入物品清单,自动搜图并下载到本地")
    ap.add_argument("items", nargs="*", help='直接写物品,如: "excavator=5" "helmet=10"')
    ap.add_argument("--items", dest="items_file", default="items.txt", help="物品清单文件 (默认 items.txt)")
    ap.add_argument("--out", default="downloads", help="下载目录 (默认 downloads)")
    ap.add_argument("--count", type=int, default=5, help="没写数量时,每个物品默认下载几张 (默认 5)")
    ap.add_argument("--min-size", type=int, default=300, help="图片最短边像素下限,过滤小图 (默认 300)")
    ap.add_argument("--timeout", type=int, default=20, help="单张图片下载超时秒数 (默认 20)")
    ap.add_argument("--safesearch", choices=["on", "moderate", "off"], default="moderate")
    args = ap.parse_args()

    if args.items:
        items = parse_items(args.items, args.count)
    else:
        p = Path(args.items_file)
        if not p.exists():
            print(f"找不到清单文件: {p.resolve()}\n"
                  f"在命令行直接写物品,或创建 items.txt (每行一个: 物品名 | 数量)")
            sys.exit(1)
        items = parse_items(p.read_text(encoding="utf-8").splitlines(), args.count)

    if not items:
        print("清单是空的。")
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"共 {len(items)} 种物品,下载到 {out_dir.resolve()}\n")
    results = []
    for name, count in items:
        print(f"[{name}] 目标 {count} 张 ...")
        results.append(
            fetch_item(name, count, out_dir, args.timeout, args.min_size, args.safesearch)
        )

    summary = write_summary(results, out_dir)
    got = sum(len(r["saved"]) for r in results)
    print(f"\n完成: 共下载 {got} 张图片。")
    print(f"汇总页面: {summary.resolve()}")


if __name__ == "__main__":
    main()
