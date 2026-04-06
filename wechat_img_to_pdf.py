#!/usr/bin/env python3
"""
微信公众号图片抓取 → PDF 生成工具
用法：
    python wechat_img_to_pdf.py <文章URL> [选项]

示例：
    python wechat_img_to_pdf.py "https://mp.weixin.qq.com/s/xxxxx"
    python wechat_img_to_pdf.py "https://mp.weixin.qq.com/s/xxxxx" -o 我的文章.pdf
    python wechat_img_to_pdf.py "https://mp.weixin.qq.com/s/xxxxx" -o output.pdf --keep-images

依赖安装：
    pip install requests beautifulsoup4 Pillow reportlab
"""

import argparse
import os
import re
import sys
import time
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
    from PIL import Image
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import io
except ImportError as e:
    print(f"[错误] 缺少依赖库：{e}")
    print("请运行：pip install requests beautifulsoup4 Pillow reportlab")
    sys.exit(1)


# ── 请求头，模拟微信内置浏览器 ──────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; Pixel 6) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36 "
        "MicroMessenger/8.0.47.2560(0x28002F39) "
        "WeChat/arm64"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://mp.weixin.qq.com/",
}

# 支持的图片 MIME 类型
IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"}

# 需要跳过的非内容图片（微信头像、表情、二维码等关键词）
SKIP_URL_KEYWORDS = [
    "qpic.cn/bizmp",   # 公众号头像
    "mmbiz_gif/",      # 动图（可按需去掉此行保留动图首帧）
    "wx_fmt=gif",
]


def log(msg: str, level: str = "INFO"):
    prefix = {"INFO": "ℹ️ ", "OK": "✅", "WARN": "⚠️ ", "ERR": "❌"}.get(level, "  ")
    print(f"{prefix} {msg}")


# ── 1. 抓取网页 ────────────────────────────────────────────────────────────
def fetch_page(url: str) -> BeautifulSoup:
    log(f"正在请求页面：{url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        log(f"页面请求失败：{e}", "ERR")
        sys.exit(1)
    log("页面获取成功", "OK")
    return BeautifulSoup(resp.text, "html.parser")


# ── 2. 提取文章标题 ────────────────────────────────────────────────────────
def extract_title(soup: BeautifulSoup) -> str:
    # 微信文章标题优先取 og:title，其次 <h1>，最后 <title>
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    title = soup.find("title")
    if title:
        return title.get_text(strip=True)
    return "微信文章"


# ── 3. 提取图片 URL ────────────────────────────────────────────────────────
def extract_image_urls(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    微信文章图片可能出现在：
      - <img src="...">
      - <img data-src="...">（懒加载）
      - <section style="background-image:url(...)">（背景图）
    """
    urls: List[str] = []
    seen: set = set()

    def add(url: str):
        url = url.strip().split("?")[0]   # 去掉 wx_fmt 等参数后重新加回去
        # 还原完整参数（微信图片 URL 含格式信息，需保留）
        pass

    def add_full(raw: str):
        if not raw or raw.startswith("data:"):
            return
        full = urljoin(base_url, raw.strip())
        # 跳过非 http 协议
        if not full.startswith("http"):
            return
        # 跳过已知非内容图片
        if any(kw in full for kw in SKIP_URL_KEYWORDS):
            return
        if full not in seen:
            seen.add(full)
            urls.append(full)

    # 文章正文容器（微信结构）
    content = soup.find(id="js_content") or soup

    # <img> 标签
    for img in content.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        add_full(src)

    # 行内背景图 style="background-image:url(...)"
    for tag in content.find_all(style=True):
        style = tag["style"]
        for match in re.finditer(r'url\(["\']?(https?://[^"\')\s]+)["\']?\)', style):
            add_full(match.group(1))

    log(f"共发现 {len(urls)} 张图片")
    return urls


# ── 4. 下载单张图片 ────────────────────────────────────────────────────────
def download_image(url: str, save_dir: str, idx: int) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type not in IMAGE_MIMES and "image" not in content_type:
            log(f"  跳过非图片资源 [{idx}]：{content_type}", "WARN")
            return None

        # 根据 content-type 确定扩展名
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
        }
        ext = ext_map.get(content_type, ".jpg")
        filename = os.path.join(save_dir, f"img_{idx:04d}{ext}")

        with open(filename, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return filename
    except Exception as e:
        log(f"  图片 [{idx}] 下载失败：{e}", "WARN")
        return None


# ── 5. 下载全部图片 ────────────────────────────────────────────────────────
def download_all(urls: List[str], save_dir: str, delay: float = 0.3) -> List[str]:
    paths = []
    total = len(urls)
    for i, url in enumerate(urls, 1):
        log(f"下载图片 [{i}/{total}]：{url[:80]}…")
        path = download_image(url, save_dir, i)
        if path:
            paths.append(path)
        time.sleep(delay)   # 礼貌性延迟，避免触发限速
    log(f"成功下载 {len(paths)} / {total} 张图片", "OK")
    return paths


# ── 6. 将图片序列打包成 PDF ────────────────────────────────────────────────
def images_to_pdf(
    image_paths: List[str],
    output_pdf: str,
    title: str = "",
    page_size=A4,
    margin: int = 30,
):
    """
    每张图片独占一页，按页面宽度等比缩放；
    若图片高度超过页面，则自动分割为多页。
    """
    if not image_paths:
        log("没有可用图片，跳过 PDF 生成", "WARN")
        return

    page_w, page_h = page_size
    content_w = page_w - 2 * margin
    content_h = page_h - 2 * margin

    c = canvas.Canvas(output_pdf, pagesize=page_size)
    c.setTitle(title)
    c.setAuthor("wechat_img_to_pdf")

    for img_path in image_paths:
        try:
            pil_img = Image.open(img_path)
        except Exception as e:
            log(f"  无法打开图片 {img_path}：{e}", "WARN")
            continue

        # WEBP / GIF 首帧转 RGB
        if pil_img.format in ("WEBP", "GIF"):
            pil_img = pil_img.convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=92)
            buf.seek(0)
            pil_img = Image.open(buf)

        img_w, img_h = pil_img.size
        if img_w == 0 or img_h == 0:
            continue

        # 按宽度缩放
        scale = content_w / img_w
        scaled_h = img_h * scale

        # 若缩放后高度超过内容区，分割渲染
        y_offset = 0          # 已渲染的原始像素高度
        remaining_h = img_h

        while remaining_h > 0:
            # 本页能放多少原始像素高度
            page_pixels = int(content_h / scale)
            chunk_pixels = min(remaining_h, page_pixels)

            # 裁切当前段
            box = (0, y_offset, img_w, y_offset + chunk_pixels)
            chunk = pil_img.crop(box)

            # 转为 ReportLab 可读的 bytes
            buf = io.BytesIO()
            fmt = "JPEG" if pil_img.mode == "RGB" else "PNG"
            chunk.save(buf, format=fmt, quality=92)
            buf.seek(0)

            draw_h = chunk_pixels * scale
            draw_y = page_h - margin - draw_h   # ReportLab 坐标原点在左下角

            c.drawImage(
                ImageReader(buf),
                margin,
                draw_y,
                width=content_w,
                height=draw_h,
                preserveAspectRatio=True,
                anchor="nw",
            )
            c.showPage()

            y_offset += chunk_pixels
            remaining_h -= chunk_pixels

    c.save()
    log(f"PDF 已生成：{output_pdf}", "OK")


# ── 主流程 ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="抓取微信公众号文章图片并生成 PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="公众号文章 URL（https://mp.weixin.qq.com/s/...）")
    parser.add_argument("-o", "--output", default="", help="输出 PDF 文件名（默认按文章标题命名）")
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="保留下载的原始图片文件夹（默认生成 PDF 后删除）",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="每次请求间隔秒数（默认 0.3，太小可能被限速）",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=30,
        help="PDF 页面四边留白（单位 pt，默认 30）",
    )
    args = parser.parse_args()

    # 1. 抓取页面
    soup = fetch_page(args.url)

    # 2. 提取标题
    title = extract_title(soup)
    log(f"文章标题：{title}")

    # 3. 提取图片 URL
    img_urls = extract_image_urls(soup, args.url)
    if not img_urls:
        log("未发现任何图片，请确认 URL 是否正确，或文章是否需要登录访问。", "WARN")
        sys.exit(0)

    # 4. 输出文件名
    if args.output:
        output_pdf = args.output
    else:
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)[:60]
        output_pdf = f"{safe_title}.pdf"

    # 5. 下载图片到临时目录
    tmp_dir = tempfile.mkdtemp(prefix="wechat_imgs_")
    log(f"临时目录：{tmp_dir}")

    try:
        image_paths = download_all(img_urls, tmp_dir, delay=args.delay)

        # 6. 生成 PDF
        images_to_pdf(
            image_paths,
            output_pdf,
            title=title,
            margin=args.margin,
        )

        # 7. 可选：保留图片
        if args.keep_images:
            keep_dir = output_pdf.replace(".pdf", "_images")
            shutil.copytree(tmp_dir, keep_dir, dirs_exist_ok=True)
            log(f"原始图片保存在：{keep_dir}", "OK")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print(f"🎉  完成！输出文件：{os.path.abspath(output_pdf)}")


if __name__ == "__main__":
    main()
