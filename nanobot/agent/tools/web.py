"""Web tools: web_search and web_fetch."""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from nanobot.agent.tools.base import Tool

# Shared constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # Limit redirects to prevent DoS attacks


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """Search the web using Brave Search API."""
    
    name = "web_search"
    description = "Search the web. Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }
    
    def __init__(self, api_key: str | None = None, max_results: int = 5):
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self.max_results = max_results
    
    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        if not query:
            return "Error: query is required"
        
        n = min(max(count or self.max_results, 1), 10)
        
        # Try Brave Search first
        if self.api_key:
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(
                        "https://api.search.brave.com/res/v1/web/search",
                        params={"q": query, "count": n},
                        headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                        timeout=10.0
                    )
                    if r.status_code == 429:
                        # Rate limited — fall through to DuckDuckGo
                        pass
                    else:
                        r.raise_for_status()
                        results = r.json().get("web", {}).get("results", [])
                        if results:
                            lines = [f"Results for: {query}\n"]
                            for i, item in enumerate(results[:n], 1):
                                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                                if desc := item.get("description"):
                                    lines.append(f"   {desc}")
                            return "\n".join(lines)
            except Exception:
                pass  # Fall through to DuckDuckGo
        
        # Fallback: DuckDuckGo HTML API (no key needed)
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=10.0,
                    follow_redirects=True,
                )
                r.raise_for_status()
                
                # Parse DuckDuckGo HTML results
                results = []
                # Find result blocks
                for match in re.finditer(
                    r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
                    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                    r.text, re.DOTALL
                ):
                    url = match.group(1)
                    title = _strip_tags(match.group(2))
                    snippet = _strip_tags(match.group(3))
                    if title and url:
                        results.append({"title": title, "url": url, "snippet": snippet})
                    if len(results) >= n:
                        break
                
                if results:
                    lines = [f"Results for: {query}\n"]
                    for i, item in enumerate(results, 1):
                        lines.append(f"{i}. {item['title']}\n   {item['url']}")
                        if item.get("snippet"):
                            lines.append(f"   {item['snippet']}")
                    return "\n".join(lines)
                
                return f"No results for: {query}"
        except Exception as e:
            return f"Search error: {e}"


class WebFetchTool(Tool):
    """Fetch and extract content from a URL using Readability."""
    
    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100}
        },
        "required": ["url"]
    }
    
    def __init__(self, max_chars: int = 50000):
        self.max_chars = max_chars
    
    async def execute(self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any) -> str:
        from readability import Document

        max_chars = maxChars or self.max_chars

        # Validate URL before fetching
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({"error": f"URL validation failed: {error_msg}", "url": url})

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
            
            ctype = r.headers.get("content-type", "")
            
            # JSON
            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2), "json"
            # HTML
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                doc = Document(r.text)
                content = self._to_markdown(doc.summary()) if extractMode == "markdown" else _strip_tags(doc.summary())
                text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                extractor = "readability"
            else:
                text, extractor = r.text, "raw"
            
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            
            return json.dumps({"url": url, "finalUrl": str(r.url), "status": r.status_code,
                              "extractor": extractor, "truncated": truncated, "length": len(text), "text": text})
        except Exception as e:
            return json.dumps({"error": str(e), "url": url})
    
    def _to_markdown(self, html_content: str) -> str:
        """Convert HTML to cleaner Markdown."""
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            h.body_width = 0  # No wrapping
            return h.handle(html_content).strip()
        except ImportError:
            # Fallback to regex-based conversion
            import re
            text = html_content
            
            # Basic cleanup
            text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL)
            
            # Simple tag replacements
            text = re.sub(r'<h1>(.*?)</h1>', r'# \1\n', text)
            text = re.sub(r'<h2>(.*?)</h2>', r'## \1\n', text)
            text = re.sub(r'<h3>(.*?)</h3>', r'### \1\n', text)
            text = re.sub(r'<p>(.*?)</p>', r'\1\n\n', text)
            text = re.sub(r'<br\s*/?>', '\n', text)
            text = re.sub(r'<li>(.*?)</li>', r'- \1\n', text)
            
            # Links
            text = re.sub(r'<a href="(.*?)".*?>(.*?)</a>', r'[\2](\1)', text)
            
            # Remove remaining tags
            text = re.sub(r'<[^>]+>', '', text)
            
            return '\n'.join(line.strip() for line in text.splitlines() if line.strip())
