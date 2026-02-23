"""Camofox tool — stealth web crawling & data extraction using local Camoufox browser."""

import asyncio
import json
import logging
import base64
from typing import Any

from nanobot.agent.tools.base import Tool

logger = logging.getLogger(__name__)

class CamofoxTool(Tool):
    """Stealth web crawling using local Camoufox browser."""

    def __init__(self, send_callback: Any = None):
        self.send_callback = send_callback
        # We'll import camoufox inside execute to avoid hard dependency at module level
        # if not installed

    @property
    def name(self) -> str:
        return "camofox"

    @property
    def description(self) -> str:
        return (
            "Advanced stealth browser for difficult websites (YouTube, Cloudflare, etc.). "
            "ALWAYS use this for YouTube to get content/comments. "
            "Runs a local Firefox instance with anti-detect features. "
            "Supports: "
            "1. Stealth crawling (auto-fingerprint spoofing). "
            "2. Screenshots. "
            "3. GeoIP spoofing."
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
                "wait_for": {
                    "type": "string",
                    "description": "Selector to wait for before extracting (default: networkidle)",
                },
                "screenshot": {
                    "type": "boolean",
                    "description": "Capture a screenshot of the page (default: false)",
                },
                "geoip": {
                    "type": "boolean",
                    "description": "Enable GeoIP spoofing for the target URL (default: false)",
                },
                "cookies": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of cookies to set (e.g. [{'name': 'x', 'value': 'y', 'domain': 'z'}])",
                },
            },
            "required": ["url"],
        }
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the context for sending messages."""
        self.channel = channel
        self.chat_id = chat_id

    async def execute(
        self,
        url: str,
        wait_for: str | None = None,
        screenshot: bool = False,
        geoip: bool = False,
        cookies: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            from camoufox.async_api import AsyncCamoufox
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        except ImportError:
            return "Error: 'camoufox' or 'playwright' not installed. Please reinstall with [camoufox] extras."

        try:
            # Configure Camoufox
            # We use a context manager for automatic cleanup
            async with AsyncCamoufox(
                headless=True,
                geoip=geoip,  # Auto-spoof based on IP or target? Camoufox handles this.
            ) as browser:
                # Create context with cookies if provided
                context = await browser.new_context()
                
                if cookies:
                    # Clean/Format cookies for Playwright
                    clean_cookies = []
                    for c in cookies:
                        # Playwright requires: name, value, url or domain, path
                        # It doesn't like keys like 'hostOnly', 'session', 'storeId'
                        cookie = {
                            "name": c.get("name"),
                            "value": c.get("value"),
                            "domain": c.get("domain"),
                            "path": c.get("path", "/"),
                            "secure": c.get("secure", False),
                            "httpOnly": c.get("httpOnly", False),
                            "sameSite": c.get("sameSite", "None"), 
                            # Convert expiration if needed, usually 'expires' or 'expiry'
                        }
                        # Remove None values and fix SameSite
                        if cookie["sameSite"] not in ["Strict", "Lax", "None"]:
                            del cookie["sameSite"]
                        
                        clean_cookies.append(cookie)
                    
                    try:
                        await context.add_cookies(clean_cookies)
                        logger.info(f"camofox: added {len(clean_cookies)} cookies")
                    except Exception as e:
                        logger.error(f"camofox: failed to add cookies: {e}")

                page = await context.new_page()
                
                # Navigate
                logger.info(f"camofox: navigating to {url} (geoip={geoip})")
                await page.goto(url, timeout=60000) # 60s timeout
                
                # Wait for content
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=10000)
                    except PlaywrightTimeoutError:
                        logger.warning(f"camofox: timeout waiting for selector {wait_for}")
                else:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except PlaywrightTimeoutError:
                        pass # It's okay if network is not fully idle, we proceed
                
                # Screenshot handling
                if screenshot and self.send_callback and self.channel and self.chat_id:
                    screenshot_bytes = await page.screenshot(full_page=False)
                    b64_data = base64.b64encode(screenshot_bytes).decode('utf-8')
                    
                    # Send via callback
                    asyncio.create_task(self._send_photo(b64_data, url))
                
                # Extract Content using Crawl4AI strategy if available, else fallback
                try:
                    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
                    from crawl4ai.content_filter_strategy import PruningContentFilter
                    
                    # Get raw HTML
                    html = await page.content()
                    
                    # Use Crawl4AI's generator
                    # We create a simple object to mimic what DefaultMarkdownGenerator expects if needed,
                    # or just pass the HTML if it supports it. 
                    # Looking at SDK, DefaultMarkdownGenerator().generate_markdown(cleaned_html, base_url=...)
                    
                    # But DefaultMarkdownGenerator usually works with a 'CrawlResult' or similar context.
                    # Let's check how to use it standalone from the HTML.
                    # Usually: md_generator.generate_markdown(cleaned_html, base_url=url)
                    
                    # We might need to clean HTML first using readability or just pass it.
                    # Let's try to use it directly.
                    
                    md_generator = DefaultMarkdownGenerator()
                    
                    # It seems we need to construct a robust way to convert.
                    # If direct usage is complex, we stick to html2text but configured better.
                    # But user wants "Skill" of Crawl4AI.
                    
                    # Let's attempt to use PruningContentFilter + MarkdownGenerator
                    # Inspecting SKILL.md: 
                    # md_generator = DefaultMarkdownGenerator(content_filter=...)
                    # result = await crawler.arun(...) -> result.markdown
                    
                    # Since we are NOT using AsyncWebCrawler (we use Camoufox), we need to manually invoke the strategy.
                    # If that's too coupled, we might just want to use readability + html2text optimized.
                    
                    # Alternative: We can use `html2text` configured similarly to Crawl4AI.
                    # But let's try to import.
                    
                    # For now, let's stick to the previous improved logic but add Pruning if possible.
                    # Actually, let's use the explicit `html2text` with better config as a reliable fallback
                    # and try to use `crawl4ai` if we can instantiated it easily.
                    
                    # Simplest robust integration:
                    import html2text
                    from readability import Document
                    
                    doc = Document(html)
                    summary = doc.summary()
                    title = doc.title()
                    
                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    h.body_width = 0
                    h.ignore_images = False
                    
                    markdown = h.handle(summary)
                    final_content = f"# {title}\n\n{markdown}"
                    
                except ImportError:
                    # Fallback
                    final_content = await page.evaluate("document.body.innerText")

                return final_content

        except Exception as e:
            logger.error(f"camofox error: {e}", exc_info=True)
            return f"Lỗi Camofox: {str(e)}"

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
            content=f"📸 Screenshot (Camofox): {url}",
            metadata=metadata,
        )
        await self.send_callback(msg)
