"""Crawl4AI tool — web crawling & data extraction via VPS-hosted Crawl4AI API."""

import asyncio
import json
import logging
from typing import Any

import aiohttp

from nanobot.agent.tools.base import Tool

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
# ── Configuration (now injected via __init__) ──────────────────────────────
EXCLUDED_SOCIAL_DOMAINS = [
    "facebook.com", "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "pinterest.com", "tiktok.com",
    "snapchat.com", "reddit.com",
]


class Crawl4AITool(Tool):
    """Advanced web crawling & structured data extraction using Crawl4AI."""

    def __init__(
        self,
        api_url: str = "http://51.222.205.231:11235",
        max_result_length: int = 12000,
        send_callback: Any = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.crawl_endpoint = f"{self.api_url}/crawl"
        self.max_result_length = max_result_length
        self.send_callback = send_callback

    @property
    def name(self) -> str:
        return "crawler"

    @property
    def description(self) -> str:
        return (
            "Crawl a web page and extract its content. "
            "Supports: "
            "1. Plain markdown extraction (default). "
            "2. Structured extraction via CSS schema or LLM instruction. "
            "3. Dynamic pages (JS), magic mode, virtual scrolling. "
            "4. Multi-step crawling via session_id (login -> crawl). "
            "5. Screenshots."
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
                    "description": "CSS selector to extract only specific elements (e.g. '.video-feed-item')",
                },
                "extraction_schema": {
                    "type": "object",
                    "description": "JSON schema for CSS-based structured extraction (e.g. {'name': 'Items', 'baseSelector': '.item', 'fields': [...]})",
                },
                "extraction_instruction": {
                    "type": "string",
                    "description": "Instruction for LLM-based extraction (e.g. 'Extract all product names and prices')",
                },
                "js_code": {
                    "type": "string",
                    "description": "JavaScript code to execute on the page before extraction",
                },
                "wait_for": {
                    "type": "string",
                    "description": "CSS selector or JS expression to wait for",
                },
                "magic": {
                    "type": "boolean",
                    "description": "Enable magic mode for anti-bot bypass (default: false)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID to reuse browser context (e.g. for multi-step flows)",
                },
                "virtual_scroll": {
                    "type": "boolean",
                    "description": "Enable virtual scrolling for infinite feeds (default: false)",
                },
                "screenshot": {
                    "type": "boolean",
                    "description": "Capture a screenshot of the page (default: false)",
                },
                "exclude_social": {
                    "type": "boolean",
                    "description": "Exclude links to social media domains from output (default: true)",
                },
                "cookies": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of cookies to set (for auth)",
                },
                "headers": {
                    "type": "object",
                    "description": "Custom HTTP headers",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        url: str,
        css_selector: str | None = None,
        extraction_schema: dict[str, Any] | None = None,
        extraction_instruction: str | None = None,
        js_code: str | None = None,
        wait_for: str | None = None,
        magic: bool = False,
        session_id: str | None = None,
        virtual_scroll: bool = False,
        scroll_count: int = 10,
        screenshot: bool = False,
        exclude_social: bool = True,
        cookies: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
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

        # Handle extraction strategies (priority: schema > instruction > css_selector)
        if extraction_schema:
            params["extraction_strategy"] = {
                "type": "JsonCssExtractionStrategy",
                "params": {"schema": extraction_schema}
            }
        elif extraction_instruction:
            params["extraction_strategy"] = {
                "type": "LLMExtractionStrategy",
                "params": {
                    "provider": "openai/gpt-4o-mini",  # Default efficient model
                    "instruction": extraction_instruction
                }
            }
        elif css_selector:
            params["css_selector"] = css_selector

        if js_code:
            params["js_code"] = js_code

        if wait_for:
            params["wait_for"] = wait_for

        if magic:
            params["magic"] = True
            params["simulate_user"] = True
            params["override_navigator"] = True
        
        if session_id:
            params["session_id"] = session_id

        if screenshot:
            params["screenshot"] = True

        if exclude_social:
            params["exclude_social_media_domains"] = EXCLUDED_SOCIAL_DOMAINS

        if virtual_scroll:
            params["scan_full_page"] = True
            params["scroll_delay"] = 1.0
            params["max_scroll_steps"] = scroll_count
            
        if cookies:
            params["cookies"] = cookies
            
        # Default headers to mimic real browser
        default_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
        }
        
        if headers:
            default_headers.update(headers)
            
        params["headers"] = default_headers

        # ── Build request payload ────────────────────────────────────
        payload = {
            "urls": [url],
            "crawler_config": {
                "type": "CrawlerRunConfig",
                "params": params,
            },
        }

        # ── Logging ──────────────────────────────────────────────────
        cookie_info = f"{len(cookies)} cookies" if cookies else "no cookies"
        header_info = f"headers={list(headers.keys())}" if headers else "no headers"
        logger.info(f"crawler: crawling {url} (magic={magic}, session={session_id}, {cookie_info}, {header_info}, extraction={bool(extraction_schema or extraction_instruction)})")

        try:
            timeout = aiohttp.ClientTimeout(total=180)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.crawl_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"Crawl4AI error ({resp.status}): {text[:300]}")
                        return f"Lỗi API Crawl4AI (status {resp.status}) tại {self.api_url}: {text[:200]}"

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

                # Main content (markdown or extracted)
                if extracted and (extraction_schema or extraction_instruction):
                     parts.append(f"\n### Dữ liệu trích xuất (Structured):\n```json\n{extracted}\n```")
                elif markdown:
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

                # Links summary
                if links and isinstance(links, dict):
                    internal = links.get("internal", [])
                    external = links.get("external", [])
                    if internal:
                        parts.append(f"\n**🔗 Links nội bộ:** {len(internal)}")
                    if external:
                        parts.append(f"**🌐 Links ngoài:** {len(external)}")

                # Screenshot handling
                ss = r.get("screenshot")
                if ss and isinstance(ss, str) and len(ss) > 100:
                    parts.append(f"\n📸 Screenshot đã chụp ({len(ss)} bytes)")
                    # Send callback if available
                    if self.send_callback and self.channel and self.chat_id:
                        try:
                            # Create a task to send photo so we don't block
                            asyncio.create_task(self._send_photo(ss, page_url))
                        except Exception as e:
                            logger.error(f"Failed to send screenshot: {e}")
                        
                output_parts.append("\n".join(parts))

            # Server stats
            proc_time = data.get("server_processing_time_s", 0)
            if proc_time:
                output_parts.append(f"\n⏱️ Thời gian xử lý: {proc_time:.1f}s")

            full_output = "\n\n---\n\n".join(output_parts)

            # Truncate if too long
            if len(full_output) > self.max_result_length:
                full_output = full_output[:self.max_result_length] + f"\n\n... (đã cắt bớt, tổng {len(full_output)} ký tự)"

            return full_output

        except asyncio.TimeoutError:
            return f"Timeout: Crawl4AI mất quá lâu khi cào {url} (>180s). Thử giảm scroll_count hoặc dùng css_selector."
        except aiohttp.ClientError as e:
            logger.error(f"Crawl4AI connection error: {e}")
            return f"Lỗi kết nối Crawl4AI: {str(e)}. Kiểm tra URL {self.api_url}."
        except Exception as e:
            logger.error(f"crawler error: {e}", exc_info=True)
            return f"Lỗi: {str(e)}"

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the context for sending messages."""
        self.channel = channel
        self.chat_id = chat_id

    async def _send_photo(self, b64_data: str, url: str) -> None:
        """Send photo via callback."""
        from nanobot.bus.events import OutboundMessage
        
        # Metadata for Telegram channel to handle as photo
        metadata = {
            "type": "photos",
            "photos": [{"base64": b64_data}],
        }
        
        msg = OutboundMessage(
            channel=self.channel,
            chat_id=self.chat_id,
            content=f"📸 Screenshot: {url}",
            metadata=metadata,
        )
        await self.send_callback(msg)
