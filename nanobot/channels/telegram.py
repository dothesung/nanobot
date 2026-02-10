"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import base64
import re
from typing import TYPE_CHECKING

from loguru import logger
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import TelegramConfig

if TYPE_CHECKING:
    from nanobot.session.manager import SessionManager


def _markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown to Telegram-safe HTML.
    """
    if not text:
        return ""
    
    # 1. Extract and protect code blocks (preserve content from other processing)
    code_blocks: list[str] = []
    def save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"
    
    text = re.sub(r'```[\w]*\n?([\s\S]*?)```', save_code_block, text)
    
    # 2. Extract and protect inline code
    inline_codes: list[str] = []
    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"
    
    text = re.sub(r'`([^`]+)`', save_inline_code, text)
    
    # 3. Headers # Title -> just the title text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)
    
    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r'^>\s*(.*)$', r'\1', text, flags=re.MULTILINE)
    
    # 5. Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 6. Links [text](url) - must be before bold/italic to handle nested cases
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    
    # 7. Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)
    
    # 9. Strikethrough ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    
    # 10. Bullet lists - item -> • item
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)
    
    # 11. Restore inline code with HTML tags
    for i, code in enumerate(inline_codes):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")
    
    # 12. Restore code blocks with HTML tags
    for i, code in enumerate(code_blocks):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")
    
    return text


# Specialized model configs for commands
SPECIALIZED_MODELS = {
    'search': {
        'url': 'https://gen.pollinations.ai/v1/chat/completions',
        'key': 'plln_sk_CtcGj14XKaIKRXm8XeqguwQiQxmZ6a6tHAMMpdrhLTxiIomsp1Qv9U9nS6HfBviF',
        'model': 'perplexity-fast',
        'system': 'Bạn là nanobot 🐈 - trợ lý tìm kiếm thông minh. Luôn trả lời bằng tiếng Việt. Tìm kiếm thông tin mới nhất và trả lời ngắn gọn, rõ ràng, có nguồn trích dẫn nếu có. Dùng emoji phù hợp.',
    },
    'vision': {
        'url': 'https://gen.pollinations.ai/v1/chat/completions',
        'key': 'plln_sk_CtcGj14XKaIKRXm8XeqguwQiQxmZ6a6tHAMMpdrhLTxiIomsp1Qv9U9nS6HfBviF',
        'model': 'gemini-fast',
        'system': 'Bạn là nanobot 🐈 - trợ lý vision thông minh. Luôn trả lời bằng tiếng Việt. Phân tích ảnh chi tiết, mô tả nội dung, nhận diện vật thể, đọc text trong ảnh. Dùng emoji phù hợp.',
    },
    'code': {
        'url': 'https://gen.pollinations.ai/v1/chat/completions',
        'key': 'plln_sk_CtcGj14XKaIKRXm8XeqguwQiQxmZ6a6tHAMMpdrhLTxiIomsp1Qv9U9nS6HfBviF',
        'model': 'qwen-coder',
        'system': 'Bạn là nanobot 🐈 - trợ lý lập trình chuyên nghiệp. Luôn trả lời bằng tiếng Việt (giải thích) nhưng code viết bằng ngôn ngữ phù hợp. Viết code sạch, có comment, có giải thích. Dùng markdown code blocks.',
    },
}

# Quick image prompt templates (short codes for callback_data)
IMAGE_QUICK_PROMPTS = {
    'cat': 'A cute kawaii cat playing with yarn, digital art, soft lighting',
    'sunset': 'A beautiful sunset over ocean with golden clouds, photography',
    'cyberpunk': 'A futuristic cyberpunk city at night with neon lights, 4k',
    'abstract': 'Abstract colorful fluid art, vibrant colors, 8k wallpaper',
    'anime': 'Beautiful anime girl in a cherry blossom garden, studio ghibli style',
    'space': 'Deep space nebula with stars and planets, sci-fi concept art, 8k',
}

# Image model display names
IMAGE_MODELS = {
    'IMAGEN_3_5': 'Imagen 3.5',
    'GEM_PIX': 'Gemini Pixel',
}

IMAGE_RATIOS = {
    'landscape': ('📐 Ngang', 'IMAGE_ASPECT_RATIO_LANDSCAPE'),
    'portrait': ('📱 Dọc', 'IMAGE_ASPECT_RATIO_PORTRAIT'),
    'square': ('⬜ Vuông', 'IMAGE_ASPECT_RATIO_SQUARE'),
}


def _parse_smart_buttons(text: str) -> tuple[str, list[list[str]]]:
    """
    Parse [buttons: A | B | C] markup from LLM response.
    
    Returns:
        (clean_text, button_rows) where button_rows is a list of rows,
        each row is a list of button labels.
    """
    import re
    
    # Match [buttons: ... ] at the end of text (single or multi-line)
    pattern = r'\[buttons:\s*(.*?)\]\s*$'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    
    if not match:
        return text, []
    
    # Strip the markup from the text
    clean_text = text[:match.start()].rstrip()
    raw_buttons = match.group(1).strip()
    
    if not raw_buttons:
        return clean_text, []
    
    # Parse button rows (split by newlines, then each row by |)
    rows = []
    for line in raw_buttons.split('\n'):
        line = line.strip()
        if not line:
            continue
        labels = [b.strip()[:30] for b in line.split('|') if b.strip()]
        if labels:
            rows.append(labels)
    
    # If single line, split into rows of 2-3 buttons
    if len(rows) == 1 and len(rows[0]) > 3:
        flat = rows[0]
        rows = [flat[i:i+2] for i in range(0, len(flat), 2)]
    
    # Max 8 buttons total
    total = 0
    limited_rows = []
    for row in rows:
        remaining = 8 - total
        if remaining <= 0:
            break
        limited_rows.append(row[:remaining])
        total += len(limited_rows[-1])
    
    return clean_text, limited_rows

class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling.
    
    Simple and reliable - no webhook/public IP needed.
    """
    
    name = "telegram"
    
    # Commands registered with Telegram's command menu (Vietnamese)
    BOT_COMMANDS = [
        BotCommand("start", "Bắt đầu trò chuyện"),
        BotCommand("reset", "Xóa lịch sử hội thoại"),
        BotCommand("search", "Tìm kiếm web"),
        BotCommand("vision", "Phân tích ảnh"),
        BotCommand("code", "Viết / sửa code"),
        BotCommand("image", "Tạo ảnh từ mô tả"),
        BotCommand("model", "Chuyển model AI"),
        BotCommand("help", "Xem danh sách lệnh"),
    ]
    
    def __init__(
        self,
        config: TelegramConfig,
        bus: MessageBus,
        groq_api_key: str = "",
        session_manager: SessionManager | None = None,
    ):
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self.groq_api_key = groq_api_key
        self.session_manager = session_manager
        self._app: Application | None = None
        self._chat_ids: dict[str, int] = {}  # Map sender_id to chat_id for replies
        self._typing_tasks: dict[str, asyncio.Task] = {}  # chat_id -> typing loop task
    
    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return
        
        self._running = True
        
        # Build the application
        builder = Application.builder().token(self.config.token)
        if self.config.proxy:
            builder = builder.proxy(self.config.proxy).get_updates_proxy(self.config.proxy)
        self._app = builder.build()
        
        # Add command handlers
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("reset", self._on_reset))
        self._app.add_handler(CommandHandler("search", self._on_search))
        self._app.add_handler(CommandHandler("vision", self._on_vision))
        self._app.add_handler(CommandHandler("code", self._on_code))
        self._app.add_handler(CommandHandler("image", self._on_image))
        self._app.add_handler(CommandHandler("model", self._on_model))
        self._app.add_handler(CommandHandler("help", self._on_help))
        
        # Add callback query handler for inline keyboards
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query))
        
        # Add photo handler for /vision caption (photo + caption is NOT a command)
        self._app.add_handler(
            MessageHandler(
                filters.PHOTO & filters.CaptionRegex(r'^/vision'),
                self._on_vision
            )
        )
        
        # Add message handler for text, photos, voice, documents
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL) 
                & ~filters.COMMAND, 
                self._on_message
            )
        )
        
        logger.info("Starting Telegram bot (polling mode)...")
        
        # Initialize and start polling
        await self._app.initialize()
        await self._app.start()
        
        # Get bot info and register command menu
        bot_info = await self._app.bot.get_me()
        logger.info(f"Telegram bot @{bot_info.username} connected")
        
        try:
            await self._app.bot.set_my_commands(self.BOT_COMMANDS)
            logger.debug("Telegram bot commands registered")
        except Exception as e:
            logger.warning(f"Failed to register bot commands: {e}")
        
        # Start polling (this runs until stopped)
        await self._app.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True  # Ignore old messages on startup
        )
        
        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False
        
        # Cancel all typing indicators
        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)
        
        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
    
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        if not self._app:
            logger.warning("Telegram bot not running")
            return
        
        # Stop typing indicator for this chat
        self._stop_typing(msg.chat_id)
        
        try:
            # chat_id should be the Telegram chat ID (integer)
            chat_id = int(msg.chat_id)
            
            # Handle photo messages from generate_image tool
            if msg.metadata.get("type") == "photos":
                photos = msg.metadata.get("photos", [])
                for i, photo_data in enumerate(photos):
                    b64 = photo_data.get("base64", "")
                    if not b64:
                        continue
                    try:
                        from io import BytesIO
                        image_bytes = base64.b64decode(b64)
                        photo_io = BytesIO(image_bytes)
                        photo_io.name = f"nanobot_image_{i+1}.jpg"
                        
                        caption = msg.content if i == 0 else None
                        await self._app.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_io,
                            caption=caption,
                            read_timeout=60,
                            write_timeout=60,
                        )
                        logger.info(f"Photo {i+1}/{len(photos)} sent to {chat_id}")
                    except Exception as e:
                        logger.error(f"Failed to send photo {i+1}: {e}")
                return  # Done, don't send text message
            
            # Parse smart buttons from LLM response
            clean_content, button_rows = _parse_smart_buttons(msg.content)
            
            # Build reply_markup if buttons found
            reply_markup = None
            if button_rows:
                keyboard = []
                for row in button_rows:
                    kb_row = []
                    for label in row:
                        # Use 'chat:' prefix + truncated label for callback_data (max 64 bytes)
                        cb_data = f"chat:{label[:28]}"
                        kb_row.append(InlineKeyboardButton(label, callback_data=cb_data))
                    keyboard.append(kb_row)
                reply_markup = InlineKeyboardMarkup(keyboard)
                logger.debug(f"Smart buttons: {[label for row in button_rows for label in row]}")
            
            # Convert markdown to Telegram HTML
            from nanobot.config.loader import load_config
            try:
                cfg = load_config()
                model_name = cfg.agents.defaults.model or "unknown"
            except Exception:
                model_name = "unknown"
            badge = f"\n\n📡 Chat · {model_name}"
            html_content = _markdown_to_telegram_html(clean_content + badge)
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=html_content,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except ValueError:
            logger.error(f"Invalid chat_id: {msg.chat_id}")
        except Exception as e:
            # Fallback to plain text if HTML parsing fails
            logger.warning(f"HTML parse failed, falling back to plain text: {e}")
            try:
                await self._app.bot.send_message(
                    chat_id=int(msg.chat_id),
                    text=msg.content
                )
            except Exception as e2:
                logger.error(f"Error sending Telegram message: {e2}")
    
    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return
        
        user = update.effective_user
        await update.message.reply_text(
            f"👋 Chào {user.first_name}! Mình là nanobot 🐈\n\n"
            "Gửi tin nhắn để trò chuyện nhé!\n"
            "Gõ /help để xem danh sách lệnh."
        )
    
    async def _on_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reset command — clear conversation history."""
        if not update.message or not update.effective_user:
            return
        
        chat_id = str(update.message.chat_id)
        session_key = f"{self.name}:{chat_id}"
        
        if self.session_manager is None:
            logger.warning("/reset called but session_manager is not available")
            await update.message.reply_text("⚠️ Quản lý phiên chưa sẵn sàng.")
            return
        
        session = self.session_manager.get_or_create(session_key)
        msg_count = len(session.messages)
        session.clear()
        self.session_manager.save(session)
        
        logger.info(f"Session reset for {session_key} (cleared {msg_count} messages)")
        await update.message.reply_text("🔄 Đã xóa lịch sử hội thoại. Bắt đầu cuộc trò chuyện mới!")
    
    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command — show available commands."""
        if not update.message:
            return
        
        help_text = (
            "🐈 <b>nanobot — Danh sách lệnh</b>\n\n"
            "💬 <b>Cơ bản</b>\n"
            "/start — Bắt đầu trò chuyện\n"
            "/reset — Xóa lịch sử hội thoại\n"
            "/help — Xem danh sách lệnh\n\n"
            "🔧 <b>Chuyên biệt</b>\n"
            "/search &lt;câu hỏi&gt; — 🔍 Tìm kiếm web (Perplexity)\n"
            "/vision — 👁️ Phân tích ảnh (gửi ảnh kèm lệnh)\n"
            "/code &lt;yêu cầu&gt; — 💻 Viết / sửa code (Qwen Coder)\n"
            "/image &lt;mô tả&gt; — 🎨 Tạo ảnh AI (Imagen)\n\n"
            "⚙️ <b>Cài đặt</b>\n"
            "/model &lt;model_id&gt; — 🔄 Chuyển model AI\n\n"
            "📝 Gửi tin nhắn bất kỳ để trò chuyện!"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")
    
    # ------------------------------------------------------------------
    # Specialized Commands
    # ------------------------------------------------------------------
    
    async def _call_specialized(self, mode: str, prompt: str, image_url: str | None = None) -> str:
        """Call a specialized model via direct HTTP POST."""
        import aiohttp
        import json
        
        config = SPECIALIZED_MODELS.get(mode)
        if not config:
            return f"❌ Chế độ '{mode}' không tồn tại."
        
        url = config['url']
        if not url.endswith('/v1/chat/completions'):
            url = url.rstrip('/') + '/v1/chat/completions'
        
        messages = [
            {"role": "system", "content": config['system']},
        ]
        
        # Vision: include image in user message
        if image_url and mode == 'vision':
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or "Hãy phân tích ảnh này."},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            })
        else:
            messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": config['model'],
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.7,
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['key']}",
        }
        
        logger.info(f"Specialized [{mode}] calling {config['model']} at {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    logger.info(f"Specialized [{mode}] response status: {resp.status}")
                    data = await resp.json()
                    
                    if resp.status != 200:
                        error = data.get("error", {})
                        msg = error.get("message", str(data)) if isinstance(error, dict) else str(error)
                        logger.error(f"Specialized [{mode}] API error: {msg}")
                        return f"❌ API Error ({resp.status}): {msg}"
                    
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if not content:
                        logger.warning(f"Specialized [{mode}] empty content, raw: {json.dumps(data)[:300]}")
                        return "❌ Không nhận được phản hồi từ model."
                    
                    logger.info(f"Specialized [{mode}] response OK ({len(content)} chars)")
                    return content
        except asyncio.TimeoutError:
            logger.error(f"Specialized [{mode}] timeout after 60s")
            return "⏰ Timeout — model phản hồi quá lâu. Thử lại sau."
        except Exception as e:
            logger.error(f"Specialized [{mode}] error: {e}")
            return f"❌ Lỗi: {str(e)}"
    
    async def _on_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /search command — web search via Perplexity."""
        if not update.message:
            return
        
        query = update.message.text.replace("/search", "", 1).strip() if update.message.text else ""
        if not query:
            await update.message.reply_text("🔍 Cách dùng: /search <câu hỏi>\n\nVí dụ: /search AI trends 2026")
            return
        
        # Start typing indicator
        str_chat_id = str(update.message.chat_id)
        self._start_typing(str_chat_id)
        
        logger.info(f"Search request: {query[:50]}...")
        result = await self._call_specialized('search', query)
        
        self._stop_typing(str_chat_id)
        
        badge = f"\n\n📡 Search · {SPECIALIZED_MODELS['search']['model']}"
        html = _markdown_to_telegram_html(f"🔍 **Kết quả tìm kiếm**\n\n{result}{badge}")
        try:
            await update.message.reply_text(html, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(result + badge)
    
    async def _on_vision(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /vision command — image analysis via Pollinations (openai model)."""
        if not update.message:
            return
        
        import base64
        import aiohttp as _aiohttp
        
        caption = update.message.caption or ""
        text = update.message.text or ""
        prompt = caption.replace("/vision", "", 1).strip() if caption else text.replace("/vision", "", 1).strip()
        
        # Check for photo
        image_b64 = None
        if update.message.photo:
            photo = update.message.photo[-1]  # Largest
            if self._app:
                try:
                    file = await self._app.bot.get_file(photo.file_id)
                    # Download photo bytes directly
                    file_url = file.file_path
                    logger.info(f"Vision: downloading photo from {file_url}")
                    async with _aiohttp.ClientSession() as sess:
                        async with sess.get(file_url, timeout=_aiohttp.ClientTimeout(total=30)) as resp:
                            image_bytes = await resp.read()
                            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                            logger.info(f"Vision: photo downloaded ({len(image_bytes)} bytes)")
                except Exception as e:
                    logger.error(f"Failed to download photo: {e}")
        
        if not image_b64:
            await update.message.reply_text(
                "👁️ Gửi ảnh kèm lệnh /vision để phân tích.\n\n"
                "Cách dùng: Gửi ảnh → viết /vision ở caption"
            )
            return
        
        str_chat_id = str(update.message.chat_id)
        self._start_typing(str_chat_id)
        
        logger.info(f"Vision request: {prompt[:50] or 'analyze image'}")
        data_url = f"data:image/jpeg;base64,{image_b64}"
        result = await self._call_specialized('vision', prompt or "Hãy phân tích chi tiết ảnh này.", data_url)
        
        self._stop_typing(str_chat_id)
        
        badge = f"\n\n📡 Vision · {SPECIALIZED_MODELS['vision']['model']}"
        html = _markdown_to_telegram_html(f"👁️ **Phân tích ảnh**\n\n{result}{badge}")
        try:
            await update.message.reply_text(html, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(result + badge)
    
    async def _on_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /code command — code generation via Qwen Coder."""
        if not update.message:
            return
        
        request = update.message.text.replace("/code", "", 1).strip() if update.message.text else ""
        if not request:
            await update.message.reply_text(
                "💻 Cách dùng: /code <yêu cầu>\n\n"
                "Ví dụ:\n"
                "• /code viết hàm fibonacci bằng Python\n"
                "• /code tạo REST API đơn giản bằng FastAPI\n"
                "• /code fix lỗi: TypeError cannot read property"
            )
            return
        
        str_chat_id = str(update.message.chat_id)
        self._start_typing(str_chat_id)
        
        logger.info(f"Code request: {request[:50]}...")
        result = await self._call_specialized('code', request)
        
        self._stop_typing(str_chat_id)
        
        badge = f"\n\n📡 Code · {SPECIALIZED_MODELS['code']['model']}"
        html = _markdown_to_telegram_html(result + badge)
        try:
            await update.message.reply_text(html, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(result + badge)
    
    async def _on_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /image command — generate images via GenPlus Imagen API."""
        if not update.message:
            return
        
        import aiohttp
        import base64
        from io import BytesIO
        
        raw = update.message.text.replace("/image", "", 1).strip() if update.message.text else ""
        if not raw:
            # Get current settings from user_data
            user_data = context.user_data or {}
            cur_ratio = user_data.get('img_ratio', 'landscape')
            cur_model = user_data.get('img_model', 'IMAGEN_3_5')
            cur_n = user_data.get('img_n', 1)
            
            ratio_label = IMAGE_RATIOS.get(cur_ratio, ('📐 Ngang',))[0]
            model_label = IMAGE_MODELS.get(cur_model, cur_model)
            
            keyboard = [
                # Quick prompts
                [InlineKeyboardButton("🐱 Mèo cute", callback_data="img:cat"),
                 InlineKeyboardButton("🌅 Hoàng hôn", callback_data="img:sunset")],
                [InlineKeyboardButton("🏙️ Cyberpunk", callback_data="img:cyberpunk"),
                 InlineKeyboardButton("🌸 Anime", callback_data="img:anime")],
                # Settings
                [InlineKeyboardButton(f"📐 Tỷ lệ: {ratio_label}", callback_data="imgset:ratio")],
                [InlineKeyboardButton(f"🤖 Model: {model_label}", callback_data="imgset:model")],
                [InlineKeyboardButton(f"🔢 Số ảnh: {cur_n}", callback_data="imgset:count")],
            ]
            await update.message.reply_text(
                "🎨 <b>Tạo ảnh AI</b>\n\n"
                "<b>Chọn nhanh</b> bên dưới hoặc gõ:\n"
                "<code>/image mô tả ảnh</code>\n\n"
                f"<b>Cài đặt hiện tại:</b>\n"
                f"• Tỷ lệ: {ratio_label}\n"
                f"• Model: {model_label}\n"
                f"• Số ảnh: {cur_n}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return
        
        # Parse options from prompt (--flags override saved settings)
        import re
        user_data = context.user_data or {}
        
        # Defaults from saved settings
        saved_ratio = user_data.get('img_ratio', 'landscape')
        n = user_data.get('img_n', 1)
        aspect_ratio = IMAGE_RATIOS.get(saved_ratio, ('', 'IMAGE_ASPECT_RATIO_LANDSCAPE'))[1]
        model = user_data.get('img_model', 'IMAGEN_3_5')
        
        # Override with --flags if specified
        m = re.search(r'--n\s+(\d+)', raw)
        if m:
            n = min(int(m.group(1)), 4)
            raw = raw[:m.start()] + raw[m.end():]
        
        m = re.search(r'--ratio\s+(landscape|portrait|square)', raw, re.IGNORECASE)
        if m:
            ratio_map = {
                'landscape': 'IMAGE_ASPECT_RATIO_LANDSCAPE',
                'portrait': 'IMAGE_ASPECT_RATIO_PORTRAIT',
                'square': 'IMAGE_ASPECT_RATIO_SQUARE',
            }
            aspect_ratio = ratio_map.get(m.group(1).lower(), aspect_ratio)
            raw = raw[:m.start()] + raw[m.end():]
        
        m = re.search(r'--model\s+(IMAGEN_3_5|GEM_PIX)', raw, re.IGNORECASE)
        if m:
            model = m.group(1).upper()
            raw = raw[:m.start()] + raw[m.end():]
        
        prompt = raw.strip()
        if not prompt:
            await update.message.reply_text("❌ Vui lòng nhập mô tả ảnh sau /image")
            return
        
        # Use the reusable _generate_image helper
        await self._generate_image(
            chat_id=update.message.chat_id,
            prompt=prompt,
            reply_target=update.message,
            aspect_ratio=aspect_ratio,
            n=n,
            model=model,
        )
    
    async def _on_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /model command — switch default model with inline keyboard."""
        if not update.message:
            return
        
        model_id = update.message.text.replace("/model", "", 1).strip() if update.message.text else ""
        
        if not model_id:
            # Show interactive model selection menu
            keyboard = [
                # GenPlus (primary)
                [InlineKeyboardButton("⭐ GenPlus Gemini", callback_data="model:genplus")],
                # GenPlus Custom Endpoint models
                [InlineKeyboardButton("🔷 Gemini 2.5 Pro", callback_data="model:gemini-2.5-pro"),
                 InlineKeyboardButton("🔷 Gemini 3 Pro", callback_data="model:gemini-3.0-pro")],
                # Pollinations free models
                [InlineKeyboardButton("⚡ Gemini Flash", callback_data="model:gemini-fast"),
                 InlineKeyboardButton("⚡ GPT-5 Nano", callback_data="model:openai-fast")],
                [InlineKeyboardButton("🧠 DeepSeek V3", callback_data="model:deepseek"),
                 InlineKeyboardButton("🔍 Perplexity", callback_data="model:perplexity-fast")],
                [InlineKeyboardButton("💻 Qwen Coder", callback_data="model:qwen-coder"),
                 InlineKeyboardButton("🌀 Mistral", callback_data="model:mistral")],
                [InlineKeyboardButton("🟢 Nova Fast", callback_data="model:nova-fast"),
                 InlineKeyboardButton("🤖 GPT-5 Mini", callback_data="model:openai")],
            ]
            await update.message.reply_text(
                "🔄 <b>Chọn Model AI</b>\n\n"
                "Bấm để chuyển model nhanh:\n\n"
                "⭐ <b>GenPlus</b> — Primary (có tool calling)\n"
                "🔷 <b>Gemini</b> — GenPlus Custom Endpoint\n"
                "⚡ <b>Free Models</b> — Pollinations AI",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return
        
        # Direct model switch via text
        await self._switch_model(update.message.chat_id, update.effective_user, model_id, update.message)
    
    async def _switch_model(self, chat_id, user, model_id: str, reply_target) -> None:
        """Switch model and send confirmation."""
        await self.bus.publish_inbound(
            InboundMessage(
                channel=self.name,
                sender_id=str(user.id) if user else "unknown",
                chat_id=str(chat_id),
                content=f"[system:model_switch:{model_id}]",
                metadata={"model_switch": model_id},
            )
        )
        await reply_target.reply_text(
            f"✅ Đã chuyển model thành <code>{model_id}</code>",
            parse_mode="HTML"
        )
    
    async def _generate_image(self, chat_id: int, prompt: str, reply_target, aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE", n: int = 1, model: str = "IMAGEN_3_5") -> None:
        """Generate image via GenPlus Imagen API and send to chat."""
        import aiohttp
        import base64
        from io import BytesIO
        
        str_chat_id = str(chat_id)
        self._start_typing(str_chat_id)
        
        logger.info(f"Image request: {prompt[:50]}... (n={n}, ratio={aspect_ratio}, model={model})")
        
        api_url = "https://tools.genplusmedia.com/api/api.php?path=/text-to-image"
        payload = {
            "prompt": prompt,
            "n": n,
            "model": model,
            "aspect_ratio": aspect_ratio,
        }
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": "Genplus123",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        self._stop_typing(str_chat_id)
                        await reply_target.reply_text(f"❌ API Error ({resp.status})")
                        return
                    data = await resp.json()
            
            panels = data.get("imagePanels", [])
            images_sent = 0
            for panel in panels:
                for img in panel.get("generatedImages", []):
                    encoded = img.get("encodedImage", "")
                    if not encoded:
                        continue
                    image_bytes = base64.b64decode(encoded)
                    photo_io = BytesIO(image_bytes)
                    photo_io.name = f"nanobot_image_{images_sent + 1}.jpg"
                    caption = f"🎨 <b>{prompt[:200]}</b>" if images_sent == 0 else None
                    try:
                        await reply_target.reply_photo(
                            photo=photo_io,
                            caption=caption,
                            parse_mode="HTML" if caption else None,
                            read_timeout=60,
                            write_timeout=60,
                        )
                        images_sent += 1
                    except Exception as e:
                        logger.error(f"Failed to send image: {e}")
            
            self._stop_typing(str_chat_id)
            if images_sent == 0:
                await reply_target.reply_text("❌ Không tạo được ảnh. Thử lại với prompt khác.")
            else:
                logger.info(f"Image: sent {images_sent} images for '{prompt[:30]}'")
        except asyncio.TimeoutError:
            self._stop_typing(str_chat_id)
            await reply_target.reply_text("⏰ Timeout — tạo ảnh quá lâu. Thử lại sau.")
        except Exception as e:
            self._stop_typing(str_chat_id)
            await reply_target.reply_text(f"❌ Lỗi: {str(e)}")
    
    async def _on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard button presses."""
        query = update.callback_query
        if not query or not query.data:
            return
        
        data = query.data
        logger.info(f"Callback query: {data} from user {query.from_user.id if query.from_user else 'unknown'}")
        
        try:
            await query.answer()  # Acknowledge the callback
        except Exception as e:
            logger.warning(f"Failed to answer callback: {e}")
        
        try:
            # --- Model selection ---
            if data.startswith("model:"):
                model_id = data.split(":", 1)[1]
                # Send model switch to agent loop bus
                await self.bus.publish_inbound(
                    InboundMessage(
                        channel=self.name,
                        sender_id=str(query.from_user.id) if query.from_user else "unknown",
                        chat_id=str(query.message.chat_id) if query.message else "",
                        content=f"[system:model_switch:{model_id}]",
                        metadata={"model_switch": model_id},
                    )
                )
                await query.edit_message_text(
                    f"✅ Đã chuyển model thành <code>{model_id}</code>",
                    parse_mode="HTML",
                )
            
            # --- Image quick prompt ---
            elif data.startswith("img:"):
                prompt_key = data.split(":", 1)[1]
                prompt = IMAGE_QUICK_PROMPTS.get(prompt_key, prompt_key)
                # Get user settings
                user_data = context.user_data or {}
                ratio_key = user_data.get('img_ratio', 'landscape')
                aspect_ratio = IMAGE_RATIOS.get(ratio_key, ('', 'IMAGE_ASPECT_RATIO_LANDSCAPE'))[1]
                img_model = user_data.get('img_model', 'IMAGEN_3_5')
                img_n = user_data.get('img_n', 1)
                
                await query.edit_message_text(
                    f"🎨 Đang tạo ảnh: <i>{prompt[:80]}...</i>",
                    parse_mode="HTML",
                )
                await self._generate_image(
                    chat_id=query.message.chat_id,
                    prompt=prompt,
                    reply_target=query.message,
                    aspect_ratio=aspect_ratio,
                    n=img_n,
                    model=img_model,
                )
            
            # --- Image settings: ratio ---
            elif data.startswith("imgset:ratio"):
                keyboard = [
                    [InlineKeyboardButton("📐 Ngang (Landscape)", callback_data="setratio:landscape")],
                    [InlineKeyboardButton("📱 Dọc (Portrait)", callback_data="setratio:portrait")],
                    [InlineKeyboardButton("⬜ Vuông (Square)", callback_data="setratio:square")],
                    [InlineKeyboardButton("« Quay lại", callback_data="imgset:back")],
                ]
                await query.edit_message_text(
                    "📐 <b>Chọn tỷ lệ ảnh:</b>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            
            elif data.startswith("setratio:"):
                ratio = data.split(":", 1)[1]
                context.user_data["img_ratio"] = ratio
                ratio_label = IMAGE_RATIOS.get(ratio, ('?',))[0]
                await query.edit_message_text(
                    f"✅ Tỷ lệ: {ratio_label}\n\nGõ <code>/image mô tả ảnh</code> hoặc bấm /image để xem menu",
                    parse_mode="HTML",
                )
            
            # --- Image settings: model ---
            elif data.startswith("imgset:model"):
                keyboard = [
                    [InlineKeyboardButton("🎨 Imagen 3.5 (mặc định)", callback_data="setmodel:IMAGEN_3_5")],
                    [InlineKeyboardButton("✨ Gemini Pixel", callback_data="setmodel:GEM_PIX")],
                    [InlineKeyboardButton("« Quay lại", callback_data="imgset:back")],
                ]
                await query.edit_message_text(
                    "🤖 <b>Chọn model tạo ảnh:</b>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            
            elif data.startswith("setmodel:"):
                model = data.split(":", 1)[1]
                context.user_data["img_model"] = model
                model_label = IMAGE_MODELS.get(model, model)
                await query.edit_message_text(
                    f"✅ Model: {model_label}\n\nGõ <code>/image mô tả ảnh</code> hoặc bấm /image để xem menu",
                    parse_mode="HTML",
                )
            
            # --- Image settings: count ---
            elif data.startswith("imgset:count"):
                keyboard = [
                    [InlineKeyboardButton("1️⃣", callback_data="setcount:1"),
                     InlineKeyboardButton("2️⃣", callback_data="setcount:2"),
                     InlineKeyboardButton("3️⃣", callback_data="setcount:3"),
                     InlineKeyboardButton("4️⃣", callback_data="setcount:4")],
                    [InlineKeyboardButton("« Quay lại", callback_data="imgset:back")],
                ]
                await query.edit_message_text(
                    "🔢 <b>Chọn số ảnh:</b>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            
            elif data.startswith("setcount:"):
                n = int(data.split(":", 1)[1])
                context.user_data["img_n"] = n
                await query.edit_message_text(
                    f"✅ Số ảnh: {n}\n\nGõ <code>/image mô tả ảnh</code> hoặc bấm /image để xem menu",
                    parse_mode="HTML",
                )
            
            # --- Back to image menu ---
            elif data == "imgset:back":
                user_data = context.user_data or {}
                cur_ratio = user_data.get('img_ratio', 'landscape')
                cur_model = user_data.get('img_model', 'IMAGEN_3_5')
                cur_n = user_data.get('img_n', 1)
                ratio_label = IMAGE_RATIOS.get(cur_ratio, ('📐 Ngang',))[0]
                model_label = IMAGE_MODELS.get(cur_model, cur_model)
                
                keyboard = [
                    [InlineKeyboardButton("🐱 Mèo cute", callback_data="img:cat"),
                     InlineKeyboardButton("🌅 Hoàng hôn", callback_data="img:sunset")],
                    [InlineKeyboardButton("🏙️ Cyberpunk", callback_data="img:cyberpunk"),
                     InlineKeyboardButton("🌸 Anime", callback_data="img:anime")],
                    [InlineKeyboardButton(f"📐 Tỷ lệ: {ratio_label}", callback_data="imgset:ratio")],
                    [InlineKeyboardButton(f"🤖 Model: {model_label}", callback_data="imgset:model")],
                    [InlineKeyboardButton(f"🔢 Số ảnh: {cur_n}", callback_data="imgset:count")],
                ]
                await query.edit_message_text(
                    "🎨 <b>Tạo ảnh AI</b>\n\n"
                    "<b>Chọn nhanh</b> hoặc gõ:\n"
                    "<code>/image mô tả ảnh</code>\n\n"
                    f"<b>Cài đặt hiện tại:</b>\n"
                    f"• Tỷ lệ: {ratio_label}\n"
                    f"• Model: {model_label}\n"
                    f"• Số ảnh: {cur_n}",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            
            # --- Smart inline button (from AI response) ---
            elif data.startswith("chat:"):
                user_text = data.split(":", 1)[1]
                user_id = str(query.from_user.id) if query.from_user else "unknown"
                username = query.from_user.username if query.from_user else None
                sender_id = f"{user_id}|{username}" if username else user_id
                chat_id = str(query.message.chat_id) if query.message else ""
                
                # Edit message to show selection
                await query.edit_message_text(
                    f"💬 {user_text}",
                )
                
                # Start typing indicator
                self._start_typing(chat_id)
                
                # Send as new message to agent loop
                await self.bus.publish_inbound(
                    InboundMessage(
                        channel=self.name,
                        sender_id=sender_id,
                        chat_id=chat_id,
                        content=user_text,
                    )
                )
                logger.info(f"Smart button: '{user_text}' from {sender_id}")
        
        except Exception as e:
            logger.error(f"Callback query error: {e}")
            try:
                await query.edit_message_text(f"❌ Lỗi: {str(e)[:100]}")
            except Exception:
                pass
    
    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        if not update.message or not update.effective_user:
            return
        
        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        
        # Use stable numeric ID, but keep username for allowlist compatibility
        sender_id = str(user.id)
        if user.username:
            sender_id = f"{sender_id}|{user.username}"
        
        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id
        
        # Build content from text and/or media
        content_parts = []
        media_paths = []
        
        # Text content
        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)
        
        # Handle media files
        media_file = None
        media_type = None
        
        if message.photo:
            media_file = message.photo[-1]  # Largest photo
            media_type = "image"
        elif message.voice:
            media_file = message.voice
            media_type = "voice"
        elif message.audio:
            media_file = message.audio
            media_type = "audio"
        elif message.document:
            media_file = message.document
            media_type = "file"
        
        # Download media if present
        if media_file and self._app:
            try:
                file = await self._app.bot.get_file(media_file.file_id)
                ext = self._get_extension(media_type, getattr(media_file, 'mime_type', None))
                
                # Save to workspace/media/
                from pathlib import Path
                media_dir = Path.home() / ".nanobot" / "media"
                media_dir.mkdir(parents=True, exist_ok=True)
                
                file_path = media_dir / f"{media_file.file_id[:16]}{ext}"
                await file.download_to_drive(str(file_path))
                
                media_paths.append(str(file_path))
                
                # Handle voice transcription
                if media_type == "voice" or media_type == "audio":
                    from nanobot.providers.transcription import GroqTranscriptionProvider
                    transcriber = GroqTranscriptionProvider(api_key=self.groq_api_key)
                    transcription = await transcriber.transcribe(file_path)
                    if transcription:
                        logger.info(f"Transcribed {media_type}: {transcription[:50]}...")
                        content_parts.append(f"[transcription: {transcription}]")
                    else:
                        content_parts.append(f"[{media_type}: {file_path}]")
                else:
                    content_parts.append(f"[{media_type}: {file_path}]")
                    
                logger.debug(f"Downloaded {media_type} to {file_path}")
            except Exception as e:
                logger.error(f"Failed to download media: {e}")
                content_parts.append(f"[{media_type}: download failed]")
        
        content = "\n".join(content_parts) if content_parts else "[empty message]"
        
        logger.debug(f"Telegram message from {sender_id}: {content[:50]}...")
        
        str_chat_id = str(chat_id)
        
        # Start typing indicator before processing
        self._start_typing(str_chat_id)
        
        # Forward to the message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str_chat_id,
            content=content,
            media=media_paths,
            metadata={
                "message_id": message.message_id,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_group": message.chat.type != "private"
            }
        )
    
    def _start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        # Cancel any existing typing task for this chat
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))
    
    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()
    
    async def _typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' action until cancelled."""
        try:
            while self._app:
                await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Typing indicator stopped for {chat_id}: {e}")
    
    def _get_extension(self, media_type: str, mime_type: str | None) -> str:
        """Get file extension based on media type."""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]
        
        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "file": ""}
        return type_map.get(media_type, "")
