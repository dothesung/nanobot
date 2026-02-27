"""Direct HTTP provider — bypasses LiteLLM for custom OpenAI-compatible endpoints."""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, Callable, Awaitable

import aiohttp

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class DirectProvider(LLMProvider):
    """
    Direct HTTP provider for custom OpenAI-compatible endpoints.

    Makes raw HTTP POST requests to the /v1/chat/completions endpoint,
    bypassing LiteLLM entirely. This ensures compatibility with any
    OpenAI-compatible API (e.g. Pollinations, LM Studio, Ollama, etc.)
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str = "",
        default_model: str = "gpt-4o",
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model

        # Normalize api_base: ensure it points to chat/completions endpoint
        base = api_base.rstrip("/")
        if "completions" in base:
            # Already a full completions URL (e.g. .../completions.php)
            self._url = base
        elif base.endswith("/v1"):
            self._url = f"{base}/chat/completions"
        else:
            self._url = f"{base}/v1/chat/completions"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        """Send a chat completion request via direct HTTP POST."""
        model = model or self.default_model

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    # Use content_type=None to skip MIME validation
                    # Some endpoints return text/html content-type with valid JSON body
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        raw = await resp.text()
                        return LLMResponse(
                            content=f"API Error: Invalid JSON response ({raw[:100]})",
                            finish_reason="error",
                        )

                    if resp.status != 200:
                        error = data.get("error", {})
                        msg = error.get("message", str(data)) if isinstance(error, dict) else str(error)
                        return LLMResponse(
                            content=f"API Error ({resp.status}): {msg}",
                            finish_reason="error",
                        )

                    response = self._parse_response(data)
                    
                    # Post-hoc streaming: feed content to callback in chunks
                    if stream_callback and response.content and not response.tool_calls:
                        await self._feed_stream_callback(response.content, stream_callback)
                    
                    return response

        except Exception as e:
            return LLMResponse(
                content=f"Error calling endpoint: {str(e)}",
                finish_reason="error",
            )

    @staticmethod
    async def _feed_stream_callback(
        content: str,
        callback: Callable[[str], Awaitable[None]],
        chunk_size: int = 12,
    ) -> None:
        """Feed already-received content to stream_callback in small chunks."""
        words = content.split()
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if i > 0:
                chunk = " " + chunk
            await callback(chunk)
            await asyncio.sleep(0.05)

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion via SSE (Server-Sent Events)."""
        model = model or self.default_model

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        # Non-streaming fallback on error
                        raw = await resp.text()
                        yield f"Error: {raw[:200]}"
                        return

                    # Parse SSE stream
                    async for line in resp.content:
                        text = line.decode("utf-8", errors="ignore").strip()
                        if not text or not text.startswith("data:"):
                            continue
                        
                        data_str = text[5:].strip()  # Remove "data: " prefix
                        
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, IndexError):
                            continue

        except Exception:
            # Fallback: use non-streaming chat
            response = await self.chat(messages=messages, model=model, max_tokens=max_tokens, temperature=temperature)
            if response.content:
                yield response.content

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse OpenAI-compatible JSON response."""
        choices = data.get("choices", [])
        if not choices:
            return LLMResponse(content="No response from API", finish_reason="error")

        choice = choices[0]
        message = choice.get("message", {})

        # Parse tool calls
        tool_calls = []
        raw_tool_calls = message.get("tool_calls", [])
        if raw_tool_calls:
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}

                tool_calls.append(ToolCallRequest(
                    id=tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=args,
                ))

        # Parse usage
        usage = {}
        raw_usage = data.get("usage", {})
        if raw_usage:
            usage = {
                "prompt_tokens": raw_usage.get("prompt_tokens", 0),
                "completion_tokens": raw_usage.get("completion_tokens", 0),
                "total_tokens": raw_usage.get("total_tokens", 0),
            }

        content = message.get("content", "")
        
        # Filter out thinking tokens (e.g. Grok thinking models)
        # Remove "Thinking about..." prefix and <think>...</think> blocks
        if content:
            import re
            # Remove <think>...</think> blocks
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            # Remove "Thinking about ..." prefix lines (Grok-style)
            content = re.sub(r'^Thinking about [^\n]*\n*', '', content).strip()

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=usage,
        )

    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model

