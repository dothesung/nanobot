"""Crawl4AI tool — web crawling & data extraction via VPS-hosted Crawl4AI API."""

import asyncio
import json
import logging
from typing import Any

import aiohttp

from nanobot.agent.tools.base import Tool

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
CRAWL4AI_URL = "http://51.222.205.231:11235"
CRAWL_ENDPOINT = f"{CRAWL4AI_URL}/crawl"

EXCLUDED_SOCIAL_DOMAINS = [
    "facebook.com", "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "pinterest.com", "tiktok.com",
    "snapchat.com", "reddit.com",
]

# Max characters to return (avoid blowing up context window)
MAX_RESULT_LENGTH = 12000


class Crawl4AITool(Tool):
    """Advanced web crawling & structured data extraction using Crawl4AI."""

    @property
    def name(self) -> str:
        return "crawler"

    @property
    def description(self) -> str:
        return (
            "Crawl a web page and extract its content as clean Markdown. "
            "Supports dynamic pages (JavaScript rendering), virtual scrolling "
            "for infinite feeds (TikTok, YouTube, Facebook), CSS selector targeting, "
            "and Magic mode for auto-extraction. "
            "Use this tool when you need to read/scrape/extract data from any website."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL of the page to crawl (required)",
                },
                "css_selector": {
                    "type": "string",
                    "description": "CSS selector to extract only specific elements (e.g. '.video-feed-item', '#main-content')",
                },
                "js_code": {
                    "type": "string",
                    "description": "JavaScript code to execute on the page before extraction (e.g. click buttons, dismiss popups)",
                },
                "wait_for": {
                    "type": "string",
                    "description": "CSS selector or JS expression to wait for before extracting (e.g. 'css:.video-list' or 'js:() => document.querySelectorAll(\".item\").length > 5')",
                },
                "magic": {
                    "type": "boolean",
                    "description": "Enable magic mode for automatic content detection and anti-bot bypass (default: false)",
                },
                "virtual_scroll": {
                    "type": "boolean",
                    "description": "Enable virtual scrolling to load infinite feed content like TikTok/YouTube (default: false)",
                },
                "scroll_count": {
                    "type": "integer",
                    "description": "Number of scrolls when virtual_scroll is enabled (default: 10)",
                },
                "screenshot": {
                    "type": "boolean",
                    "description": "Capture a screenshot of the page (default: false)",
                },
                "exclude_social": {
                    "type": "boolean",
                    "description": "Exclude links to social media domains from output (default: true)",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        url: str,
        css_selector: str | None = None,
        js_code: str | None = None,
        wait_for: str | None = None,
        magic: bool = False,
        virtual_scroll: bool = False,
        scroll_count: int = 10,
        screenshot: bool = False,
        exclude_social: bool = True,
        **kwargs: Any,
    ) -> str:
        # ── Auto-detect social media URLs ─────────────────────────────
        SOCIAL_DOMAINS = ["tiktok.com", "youtube.com", "instagram.com", "x.com", "twitter.com", "facebook.com"]
        is_social = any(d in url.lower() for d in SOCIAL_DOMAINS)

        if is_social:
            # Social media sites need magic mode + anti-bot
            magic = True
            # Don't exclude social domains when crawling social media itself
            exclude_social = False
            # Remove wait_for — social media selectors are unreliable
            if wait_for:
                logger.info(f"crawler: removing wait_for '{wait_for}' for social media URL")
                wait_for = None

        # ── Build crawler_config params ──────────────────────────────
        params: dict[str, Any] = {
            "scraping_strategy": {
                "type": "LXMLWebScrapingStrategy",
                "params": {},
            },
            "page_timeout": 120000,  # 120s for slow/dynamic pages
        }

        if css_selector:
            params["css_selector"] = css_selector

        if js_code:
            params["js_code"] = js_code

        if wait_for:
            params["wait_for"] = wait_for

        if magic:
            params["magic"] = True
            params["simulate_user"] = True
            params["override_navigator"] = True

        if screenshot:
            params["screenshot"] = True

        if exclude_social:
            params["exclude_social_media_domains"] = EXCLUDED_SOCIAL_DOMAINS

        if virtual_scroll:
            params["scan_full_page"] = True
            params["scroll_delay"] = 1.0
            params["max_scroll_steps"] = scroll_count

        # ── Build request payload ────────────────────────────────────
        payload = {
            "urls": [url],
            "crawler_config": {
                "type": "CrawlerRunConfig",
                "params": params,
            },
        }

        logger.info(f"crawler: crawling {url} (magic={magic}, virtual_scroll={virtual_scroll}, social={is_social})")

        try:
            timeout = aiohttp.ClientTimeout(total=180)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    CRAWL_ENDPOINT,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"Crawl4AI error ({resp.status}): {text[:300]}")
                        return f"Lỗi API Crawl4AI (status {resp.status}): {text[:200]}"

                    data = await resp.json()

            # ── Parse response ───────────────────────────────────────
            # Response format: {"success": true, "results": [{...}], ...}
            if not data.get("success"):
                return f"Crawl4AI thất bại: {json.dumps(data, ensure_ascii=False)[:500]}"

            results = data.get("results", [])
            if not results:
                return "Crawl4AI trả về 0 kết quả."

            # ── Extract content from results ─────────────────────────
            output_parts = []
            for r in results:
                page_url = r.get("url", url)
                markdown = r.get("markdown", "")
                extracted = r.get("extracted_content", "")
                metadata = r.get("metadata", {})
                links = r.get("links", {})
                media = r.get("media", {})
                tables = r.get("tables", [])
                status_code = r.get("status_code", 0)
                error_msg = r.get("error_message", "")

                if error_msg:
                    output_parts.append(f"⚠️ Lỗi khi cào {page_url}: {error_msg}")
                    continue

                # Header with metadata
                parts = [f"## 📄 {page_url} (HTTP {status_code})"]

                # Metadata
                if metadata and isinstance(metadata, dict):
                    title = metadata.get("title", "")
                    desc = metadata.get("description", "")
                    if title:
                        parts.append(f"**Tiêu đề:** {title}")
                    if desc:
                        parts.append(f"**Mô tả:** {desc}")

                # Main content (markdown)
                if markdown:
                    parts.append(f"\n### Nội dung:\n{markdown}")
                elif extracted:
                    parts.append(f"\n### Nội dung trích xuất:\n{extracted}")

                # Media summary
                if media and isinstance(media, dict):
                    images = media.get("images", [])
                    videos = media.get("videos", [])
                    if images:
                        parts.append(f"\n**🖼️ Hình ảnh:** {len(images)} ảnh")
                        for img in images[:5]:
                            src = img.get("src", "") if isinstance(img, dict) else str(img)
                            if src:
                                parts.append(f"  - {src}")
                    if videos:
                        parts.append(f"\n**🎬 Video:** {len(videos)} video")
                        for vid in videos[:5]:
                            src = vid.get("src", "") if isinstance(vid, dict) else str(vid)
                            if src:
                                parts.append(f"  - {src}")

                # Links summary
                if links and isinstance(links, dict):
                    internal = links.get("internal", [])
                    external = links.get("external", [])
                    if internal:
                        parts.append(f"\n**🔗 Links nội bộ:** {len(internal)}")
                    if external:
                        parts.append(f"**🌐 Links ngoài:** {len(external)}")

                # Tables summary
                if tables:
                    parts.append(f"\n**📊 Bảng dữ liệu:** {len(tables)}")

                # Screenshot
                ss = r.get("screenshot")
                if ss and isinstance(ss, str) and len(ss) > 100:
                    parts.append(f"\n📸 Screenshot đã chụp ({len(ss)} bytes)")

                output_parts.append("\n".join(parts))

            # Server stats
            proc_time = data.get("server_processing_time_s", 0)
            if proc_time:
                output_parts.append(f"\n⏱️ Thời gian xử lý: {proc_time:.1f}s")

            full_output = "\n\n---\n\n".join(output_parts)

            # Truncate if too long
            if len(full_output) > MAX_RESULT_LENGTH:
                full_output = full_output[:MAX_RESULT_LENGTH] + f"\n\n... (đã cắt bớt, tổng {len(full_output)} ký tự)"

            return full_output

        except asyncio.TimeoutError:
            return f"Timeout: Crawl4AI mất quá lâu khi cào {url} (>180s). Thử giảm scroll_count hoặc dùng css_selector."
        except aiohttp.ClientError as e:
            logger.error(f"Crawl4AI connection error: {e}")
            return f"Lỗi kết nối Crawl4AI: {str(e)}. Kiểm tra VPS ({CRAWL4AI_URL}) có đang chạy không."
        except Exception as e:
            logger.error(f"crawler error: {e}", exc_info=True)
            return f"Lỗi: {str(e)}"
