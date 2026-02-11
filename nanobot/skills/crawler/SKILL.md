---
name: crawler
description: Cào dữ liệu web và trích xuất nội dung bằng Crawl4AI. Hỗ trợ Social Media (TikTok, YouTube), cuộn trang vô tận, và CSS selector.
---

# Crawler — Cào & Trích xuất Dữ liệu Web

## ⚠️ Sử dụng tool `crawler` trực tiếp, KHÔNG dùng exec!

```
crawler(url="https://example.com")
```

## Tham số

| Tham số | Kiểu | Mặc định | Mô tả |
|---------|-------|----------|-------|
| `url` | string | *(bắt buộc)* | URL cần cào |
| `css_selector` | string | — | Chỉ lấy nội dung trong selector (VD: `.main-content`) |
| `js_code` | string | — | JavaScript chạy trước khi trích xuất |
| `wait_for` | string | — | Đợi element xuất hiện (`css:.selector` hoặc `js:() => bool`) |
| `magic` | bool | false | Chế độ tự nhận diện nội dung + anti-bot |
| `virtual_scroll` | bool | false | Cuộn trang tự động (cho TikTok/YouTube) |
| `scroll_count` | int | 10 | Số lần cuộn khi `virtual_scroll=true` |
| `screenshot` | bool | false | Chụp ảnh trang |
| `exclude_social` | bool | true | Loại bỏ link mạng xã hội |

## Ví dụ Sử dụng

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

## Khi nào dùng tool này
- Khi user yêu cầu **cào/scrape/crawl** trang web
- Khi cần **lấy nội dung** từ URL để phân tích
- Khi cần **theo dõi/monitor** trang web, kênh Social Media
- Khi WebFetch không đủ (trang cần JS rendering)

## Output
- Trả về nội dung trang dạng **Markdown** (sạch, dễ đọc)
- Tự động giới hạn 12000 ký tự để không tràn context
