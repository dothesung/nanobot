"""Image generation tool — calls GenPlus Imagen API and sends photos to chat."""

import asyncio
import base64
import json
import logging
from typing import Any, Callable, Awaitable

import aiohttp

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage

logger = logging.getLogger(__name__)

API_URL = "https://tools.genplusmedia.com/api/api.php?path=/text-to-image"
API_KEY = "Genplus123"

RATIO_MAP = {
    "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "square": "IMAGE_ASPECT_RATIO_SQUARE",
    "16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "9:16": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "1:1": "IMAGE_ASPECT_RATIO_SQUARE",
}


class GenerateImageTool(Tool):
    """Generate images from text prompts and send them directly to chat."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ):
        self._send_callback = send_callback
        self._default_channel = ""
        self._default_chat_id = ""

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current chat context."""
        self._default_channel = channel
        self._default_chat_id = chat_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        self._send_callback = callback

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return (
            "Generate AI images from a text prompt and send them directly to the chat. "
            "Supports Vietnamese and English prompts. Use this when the user asks to "
            "create, draw, generate, or make images/illustrations/artwork/photos."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate (Vietnamese or English)",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of images to generate (1-4, default: 1)",
                },
                "ratio": {
                    "type": "string",
                    "description": "Aspect ratio: landscape (16:9), portrait (9:16), or square (1:1). Default: landscape",
                    "enum": ["landscape", "portrait", "square"],
                },
                "model": {
                    "type": "string",
                    "description": "AI model: IMAGEN_3_5 (best quality) or GEM_PIX (fast). Default: IMAGEN_3_5",
                    "enum": ["IMAGEN_3_5", "GEM_PIX"],
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str,
        n: int = 1,
        ratio: str = "landscape",
        model: str = "IMAGEN_3_5",
        **kwargs: Any,
    ) -> str:
        chat_id = self._default_chat_id
        channel = self._default_channel

        if not chat_id or not channel:
            return "Error: No chat context available"

        n = min(max(n, 1), 4)
        aspect_ratio = RATIO_MAP.get(ratio, "IMAGE_ASPECT_RATIO_LANDSCAPE")

        payload = {
            "prompt": prompt,
            "n": n,
            "model": model,
            "aspect_ratio": aspect_ratio,
        }
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        }

        logger.info(f"generate_image: '{prompt[:60]}' (n={n}, ratio={ratio}, model={model})")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"Image API error: {text[:300]}")
                        return f"Lỗi API (status {resp.status}): {text[:200]}"
                    data = await resp.json()

            # Collect base64 images
            photos = []
            panels = data.get("imagePanels", [])
            for panel in panels:
                for img in panel.get("generatedImages", []):
                    encoded = img.get("encodedImage", "")
                    if encoded:
                        photos.append({
                            "base64": encoded,
                            "seed": img.get("seed"),
                            "model": img.get("modelNameType", model),
                        })

            if not photos:
                return "Không tạo được ảnh. Thử thay đổi prompt hoặc model khác."

            # Send via OutboundMessage with photos in metadata
            if self._send_callback:
                msg = OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=f"🎨 {prompt[:200]}",
                    metadata={
                        "type": "photos",
                        "photos": photos,
                        "model": model,
                        "ratio": ratio,
                    },
                )
                await self._send_callback(msg)

            seeds = [str(p["seed"]) for p in photos if p.get("seed")]
            seed_info = f" | Seeds: {', '.join(seeds)}" if seeds else ""
            return f"✅ Đã tạo và gửi {len(photos)} ảnh thành công! Model: {model}, Tỷ lệ: {ratio}{seed_info}"

        except asyncio.TimeoutError:
            return "Timeout: API tạo ảnh quá lâu (>120s). Thử lại sau."
        except Exception as e:
            logger.error(f"generate_image error: {e}")
            return f"Lỗi: {str(e)}"
