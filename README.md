# wechat-img-to-pdf

一个命令行工具，将微信公众号文章中的图片抓取下来，自动打包生成 PDF 文件。

---

## ✨ 功能特性

- 🔗 只需粘贴文章链接，一条命令完成抓取 → 下载 → 生成 PDF 全流程
- 🖼️ 支持懒加载图片（`data-src`）和 CSS 背景图（`background-image`）
- 📄 超长图片自动分页，完整保留内容不截断
- 🎨 支持 JPG、PNG、WebP、GIF（取首帧）、BMP 格式
- 🧹 自动过滤头像、表情包等无关图片
- 🐢 请求间隔可调，避免触发微信限速
- 🐍 兼容 Python 3.7+

---

## 📦 安装依赖

```bash
pip install requests beautifulsoup4 Pillow reportlab
```

---

## 🚀 使用方法

**最简用法**（PDF 自动以文章标题命名）

```bash
python wechat_img_to_pdf.py "https://mp.weixin.qq.com/s/xxxxx"
```

**指定输出文件名**

```bash
python wechat_img_to_pdf.py "https://mp.weixin.qq.com/s/xxxxx" -o 我的文章.pdf
```

**生成 PDF 的同时保留原始图片**

```bash
python wechat_img_to_pdf.py "https://mp.weixin.qq.com/s/xxxxx" -o output.pdf --keep-images
```

**调整请求间隔（网络慢或遇到限速时加大）**

```bash
python wechat_img_to_pdf.py "https://mp.weixin.qq.com/s/xxxxx" --delay 1.0
```

---

## ⚙️ 全部参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `url` | 公众号文章链接（必填） | — |
| `-o`, `--output` | 输出 PDF 文件路径 | 自动按文章标题命名 |
| `--keep-images` | 保留下载的原始图片文件夹 | 否（生成后自动清理） |
| `--delay` | 每次图片请求的间隔秒数 | `0.3` |
| `--margin` | PDF 页面四边留白（单位 pt） | `30` |

---

## ⚠️ 注意事项

- **需要登录的文章**：部分付费或粉丝专属内容需要微信登录才能访问，脚本无法直接获取。可在浏览器登录后，通过开发者工具复制完整 Cookie，添加到脚本的 `HEADERS` 字典中再运行。
- **仅限个人使用**：请遵守微信平台使用协议，勿用于商业目的或大规模批量爬取。
- **文章有效期**：微信文章链接可能因作者删除而失效，请及时保存。
