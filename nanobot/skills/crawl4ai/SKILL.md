---
name: crawl4ai
description: Complete toolkit for web crawling and data extraction. Use the `crawler` tool directly to scrape any website. Supports social media (TikTok, YouTube), GitHub, JavaScript-heavy pages, structured data extraction, and batch crawling.
version: 0.7.4
last_updated: 2026-02-23
---

# Crawl4AI — Cào & Trích xuất Dữ liệu Web

## ⚠️ QUAN TRỌNG — Quy tắc bắt buộc

> **LUÔN LUÔN gọi tool `crawler` trực tiếp.**
> **KHÔNG BAO GIỜ** dùng `exec` để `import crawl4ai` hoặc chạy Python scripts.
> **KHÔNG BAO GIỜ** dùng `exec` để chạy Docker commands.
> Tool `crawler` gọi API server Crawl4AI từ xa — không cần cài thư viện local.

```
# ✅ ĐÚNG — Gọi tool trực tiếp
crawler(url="https://example.com")

# ❌ SAI — KHÔNG làm thế này
exec(command="python -c 'from crawl4ai import ...'")
exec(command="docker exec crawl4ai ...")
```

---

## ⚡ Sử dụng Tool `crawler`

### Tham số

| Tham số | Kiểu | Mặc định | Mô tả |
|---------|-------|----------|-------|
| `url` | string | *(bắt buộc)* | URL cần cào |
| `css_selector` | string | — | Chỉ lấy nội dung trong selector (VD: `.main-content`) |
| `extraction_schema` | object | — | JSON schema cho CSS-based extraction |
| `extraction_instruction` | string | — | Instruction cho LLM-based extraction |
| `js_code` | string | — | JavaScript chạy trước khi trích xuất |
| `wait_for` | string | — | Đợi element xuất hiện (`css:.selector` hoặc `js:() => bool`) |
| `magic` | bool | false | Chế độ tự nhận diện nội dung + anti-bot |
| `session_id` | string | — | Reuse browser context (multi-step flows) |
| `virtual_scroll` | bool | false | Cuộn trang tự động (cho TikTok/YouTube) |
| `scroll_count` | int | 10 | Số lần cuộn khi `virtual_scroll=true` |
| `screenshot` | bool | false | Chụp ảnh trang |
| `exclude_social` | bool | true | Loại bỏ link mạng xã hội |
| `cookies` | array | — | Cookies cho auth |
| `headers` | object | — | Custom HTTP headers |

---

## 📖 Ví dụ Sử dụng

### Cào trang cơ bản
```
crawler(url="https://vnexpress.net")
```

### Cào kênh TikTok (cuộn trang)
```
crawler(url="https://www.tiktok.com/@user", virtual_scroll=true, scroll_count=15)
```

### Lấy dữ liệu cụ thể với CSS selector
```
crawler(url="https://youtube.com/@channel/videos", css_selector="#contents ytd-rich-item-renderer")
```

### Dùng Magic Mode (anti-bot)
```
crawler(url="https://protected-site.com", magic=true)
```

### Chạy JavaScript trước khi cào
```
crawler(url="https://example.com", js_code="document.querySelector('.load-more').click()", wait_for="css:.new-items")
```

### Structured extraction với schema
```
crawler(url="https://shop.com", extraction_schema={"name": "Products", "baseSelector": ".product", "fields": [{"name": "title", "selector": "h2", "type": "text"}, {"name": "price", "selector": ".price", "type": "text"}]})
```

### Multi-step login rồi cào
```
crawler(url="https://site.com/login", session_id="my_session", js_code="document.querySelector('#user').value='admin'; document.querySelector('#pass').value='123'; document.querySelector('#submit').click();", wait_for="css:.dashboard")
crawler(url="https://site.com/data", session_id="my_session")
```

---

## 🎬 Cào YouTube

> **QUAN TRỌNG:** YouTube dùng Web Components nặng, tool `crawler` (Crawl4AI API) thường trả markdown rỗng.
> **Luôn dùng tool `camofox`** cho YouTube — nó chạy Playwright local, render JS đầy đủ.

### Cào thông tin video + comments
```
camofox(url="https://www.youtube.com/watch?v=VIDEO_ID")
```

### Cào danh sách video từ channel
```
camofox(url="https://www.youtube.com/@channel/videos")
```

### Tips cào YouTube
- **Luôn dùng `camofox`**, KHÔNG dùng `crawler` cho YouTube
- **KHÔNG dùng `extraction_instruction`** — gây lỗi 500
- Kết quả trả về dạng markdown — tự phân tích nội dung từ đó

---

## 🐙 Cào GitHub

### Cào Repository (README, code, file structure)
```
crawler(url="https://github.com/owner/repo")
```

### Cào Issues / Pull Requests
```
crawler(url="https://github.com/owner/repo/issues")
crawler(url="https://github.com/owner/repo/issues/123")
crawler(url="https://github.com/owner/repo/pulls")
```

### Cào Profile / Organization
```
crawler(url="https://github.com/username")
crawler(url="https://github.com/orgs/orgname")
```

### Cào Releases & Tags
```
crawler(url="https://github.com/owner/repo/releases")
```

### Cào File cụ thể (raw content)
```
crawler(url="https://raw.githubusercontent.com/owner/repo/main/README.md")
```

### Cào GitHub Search Results
```
crawler(url="https://github.com/search?q=crawl4ai+language:python&type=repositories")
```

### Tips cào GitHub
- Dùng URL `raw.githubusercontent.com` để lấy raw file content
- Dùng `css_selector` để focus vào phần cụ thể (VD: `.markdown-body` cho README)
- GitHub API (`api.github.com`) trả về JSON — dùng `web_fetch` thay vì `crawler`
- Với trang private, cần auth headers hoặc dùng `gh` CLI (xem skill `github`)

---

## Khi nào dùng tool `crawler`
- Khi user yêu cầu **cào/scrape/crawl** trang web
- Khi cần **lấy nội dung** từ URL để phân tích
- Khi cần **theo dõi/monitor** trang web, kênh Social Media
- Khi WebFetch không đủ (trang cần JS rendering)

## Output
- Trả về nội dung trang dạng **Markdown** (sạch, dễ đọc)
- Bao gồm metadata (tiêu đề, mô tả), links, media
- Tự động giới hạn 12000 ký tự để không tràn context

## Tham khảo thêm
- Xem `references/complete-sdk-reference.md` để tra cứu SDK parameters nâng cao
- Xem `scripts/` để chạy batch crawling hoặc extraction pipeline thủ công
