"""Image generation tool — calls GenPlus Imagen API and sends photos to chat."""

import asyncio
import base64
import json
import logging
import os
from typing import Any, Callable, Awaitable

import aiohttp

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage

logger = logging.getLogger(__name__)

API_URL_T2I = "https://tools.genplusmedia.com/api/api.php?path=/text-to-image"
API_URL_I2I = "https://tools.genplusmedia.com/api/api.php?path=/workflow/image-to-image"
API_URL_EDIT = "https://tools.genplusmedia.com/api/api.php?path=/workflow/edit-image"
API_KEY = os.environ.get("GENPLUS_API_KEY", "Genplus123")

RATIO_MAP = {
    "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "square": "IMAGE_ASPECT_RATIO_SQUARE",
    "16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "9:16": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "1:1": "IMAGE_ASPECT_RATIO_SQUARE",
}

def _read_image_base64(filepath: str) -> str | None:
    """Reads a local image file and returns its base64 string."""
    try:
        if filepath.startswith("file://"):
            filepath = filepath[7:]

        import os
        if not os.path.exists(filepath):
            logger.error(f"Image file not found: {filepath}")
            return None

        with open(filepath, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
            return encoded
    except Exception as e:
        logger.error(f"Error reading image {filepath}: {e}")
        return None


def _extract_photos(data: dict, default_model: str = "WORKFLOW") -> list[dict]:
    """Extract photos from API response, handling both flat and nested formats."""
    photos = []
    
    # Try flat imagePanels first (text-to-image style)
    panels = data.get("imagePanels", [])
    
    # Try nested result.data.json.result.imagePanels (workflow style)
    if not panels and "result" in data:
        nested = data["result"]
        if isinstance(nested, dict):
            if "data" in nested:
                nested = nested.get("data", {}).get("json", {}).get("result", {})
            panels = nested.get("imagePanels", []) if isinstance(nested, dict) else []
    
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        for img in panel.get("generatedImages", []):
            encoded = img.get("encodedImage", "")
            if encoded:
                photos.append({
                    "base64": encoded,
                    "seed": img.get("seed"),
                    "model": img.get("modelNameType", default_model),
                })
    
    return photos


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
                    "description": "AI model: GEM_PIX (best quality) or IMAGEN_3_5 (fast). Default: GEM_PIX",
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
        model: str = "GEM_PIX",
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
            async with aiohttp.ClientSession() as session_http:
                async with session_http.post(
                    API_URL_T2I,
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


class ImageToImageTool(Tool):
    """Modify or restyle an existing image using image-to-image API."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ):
        self._send_callback = send_callback
        self._default_channel = ""
        self._default_chat_id = ""

    def set_context(self, channel: str, chat_id: str) -> None:
        self._default_channel = channel
        self._default_chat_id = chat_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        self._send_callback = callback

    @property
    def name(self) -> str:
        return "image_to_image"

    @property
    def description(self) -> str:
        return (
            "Modify or restyle a local image using a text prompt. "
            "Use this when the user wants to apply a specific style (e.g., cyberpunk, anime, watercolor) "
            "to their existing photo. Accepts one image at a time."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the style or changes to apply (Vietnamese or English)",
                },
                "image_path": {
                    "type": "string",
                    "description": "Absolute path to the local image file to transform",
                },
                "ratio": {
                    "type": "string",
                    "description": "Aspect ratio: landscape, portrait, or square. Defaults to landscape.",
                    "enum": ["landscape", "portrait", "square"],
                },
            },
            "required": ["prompt", "image_path"],
        }

    async def execute(
        self,
        prompt: str,
        image_path: str,
        ratio: str = "landscape",
        **kwargs: Any,
    ) -> str:
        chat_id = self._default_chat_id
        channel = self._default_channel

        if not chat_id or not channel:
            return "Error: No chat context available"

        if not image_path:
            return "Error: Bạn phải cung cấp đường dẫn ảnh (image_path)."

        b64_img = _read_image_base64(image_path)
        if not b64_img:
            return f"Error: Không thể đọc hoặc tìm thấy file ảnh: {image_path}"

        aspect_ratio = RATIO_MAP.get(ratio, "IMAGE_ASPECT_RATIO_LANDSCAPE")

        payload = {
            "prompt": prompt,
            "base64_image": b64_img,
            "aspect_ratio": aspect_ratio,
        }

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        }

        logger.info(f"image_to_image: '{prompt[:60]}' (ratio={ratio})")

        try:
            async with aiohttp.ClientSession() as session_http:
                async with session_http.post(
                    API_URL_I2I,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"Image API error: {text[:300]}")
                        return f"Lỗi API (status {resp.status}): {text[:200]}"
                    data = await resp.json()

            photos = _extract_photos(data, "I2I_WORKFLOW")

            if not photos:
                # I2I may return mediaGenerationId for async processing
                gen_id = None
                if "mediaGenerationId" in data:
                    gen_id = data["mediaGenerationId"]
                elif "result" in data:
                    nested = data["result"]
                    if isinstance(nested, dict) and "data" in nested:
                        nested = nested["data"].get("json", {}).get("result", {})
                    gen_id = nested.get("mediaGenerationId")
                if gen_id:
                    return f"⏳ Ảnh đang được tạo (ID: {gen_id[:30]}...). Workflow I2I sẽ xử lý async."
                return "Không tạo được ảnh. Thử thay đổi prompt hoặc dùng ảnh có nội dung rõ ràng hơn."

            if self._send_callback:
                msg = OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=f"🎨 Chỉnh sửa ảnh I2I: {prompt[:200]}",
                    metadata={
                        "type": "photos",
                        "photos": photos,
                        "model": "I2I_WORKFLOW",
                        "ratio": ratio,
                    },
                )
                await self._send_callback(msg)

            return f"✅ Đã tạo và gửi {len(photos)} ảnh thành công! Tỷ lệ: {ratio}"

        except asyncio.TimeoutError:
            return "Timeout: API I2I chạy quá lâu (>180s). Thử lại sau."
        except Exception as e:
            logger.error(f"image_to_image error: {e}")
            return f"Lỗi sys: {str(e)}"


class EditImageTool(Tool):
    """Edit or inpaint specific regions of an image using a mask."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ):
        self._send_callback = send_callback
        self._default_channel = ""
        self._default_chat_id = ""

    def set_context(self, channel: str, chat_id: str) -> None:
        self._default_channel = channel
        self._default_chat_id = chat_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        self._send_callback = callback

    @property
    def name(self) -> str:
        return "edit_image"

    @property
    def description(self) -> str:
        return (
            "Edit or replace specific parts of an image using an original photo, a mask photo, and a text prompt. "
            "Use this for inpainting tasks (e.g., 'Remove the object and replace it with a dog')."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the replacement or desired content.",
                },
                "original_image_path": {
                    "type": "string",
                    "description": "Absolute path to the original local image file.",
                },
                "mask_image_path": {
                    "type": "string",
                    "description": "Absolute path to the mask local image file specifying the region to edit.",
                },
                "ratio": {
                    "type": "string",
                    "description": "Aspect ratio: landscape, portrait, or square. Defaults to landscape.",
                    "enum": ["landscape", "portrait", "square"],
                },
            },
            "required": ["prompt", "original_image_path", "mask_image_path"],
        }

    async def execute(
        self,
        prompt: str,
        original_image_path: str,
        mask_image_path: str,
        ratio: str = "landscape",
        **kwargs: Any,
    ) -> str:
        chat_id = self._default_chat_id
        channel = self._default_channel

        if not chat_id or not channel:
            return "Error: No chat context available"

        original_b64 = _read_image_base64(original_image_path)
        if not original_b64:
            return f"Error: Không thể đọc file ảnh gốc: {original_image_path}"

        mask_b64 = _read_image_base64(mask_image_path)
        if not mask_b64:
            return f"Error: Không thể đọc file mask: {mask_image_path}"

        aspect_ratio = RATIO_MAP.get(ratio, "IMAGE_ASPECT_RATIO_LANDSCAPE")
        
        payload = {
            "prompt": prompt,
            "original_base64": original_b64,
            "mask_base64": mask_b64,
            "aspect_ratio": aspect_ratio,
        }

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        }

        logger.info(f"edit_image: '{prompt[:60]}' (ratio={ratio})")

        try:
            async with aiohttp.ClientSession() as session_http:
                async with session_http.post(
                    API_URL_EDIT,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"Image API error: {text[:300]}")
                        return f"Lỗi API (status {resp.status}): {text[:200]}"
                    data = await resp.json()

            photos = _extract_photos(data, "EDIT_WORKFLOW")

            if not photos:
                return "Không tạo được ảnh edit (inpainting). Thử điều chỉnh mask hoặc prompt."

            if self._send_callback:
                msg = OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=f"🖌 Inpainting ảnh: {prompt[:200]}",
                    metadata={
                        "type": "photos",
                        "photos": photos,
                        "model": "EDIT_WORKFLOW",
                        "ratio": ratio,
                    },
                )
                await self._send_callback(msg)

            return f"✅ Đã edit và gửi ảnh thành công! Tỷ lệ: {ratio}"

        except asyncio.TimeoutError:
            return "Timeout: API Inpainting chạy quá lâu (>180s). Thử lại sau."
        except Exception as e:
            logger.error(f"edit_image error: {e}")
            return f"Lỗi sys: {str(e)}"
