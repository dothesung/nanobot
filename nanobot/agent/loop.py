"""Agent loop: the core processing engine."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage, ProgressMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.image_gen import GenerateImageTool
from nanobot.agent.tools.crawler import Crawl4AITool
from nanobot.agent.subagent import SubagentManager
from nanobot.session.manager import SessionManager


class AgentLoop:
    """
    The agent loop is the core processing engine.
    
    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """
    
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        memory_window: int = 40,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        crawler_config: "CrawlerConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig, CrawlerConfig
        from nanobot.cron.service import CronService
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.memory_window = memory_window
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.crawler_config = crawler_config or CrawlerConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        
        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )
        
        self._running = False
        self._chat_models: dict[str, str] = {}  # per-chat model overrides: session_key -> model
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        # File tools (restrict to workspace if configured)
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
        self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
        self.tools.register(EditFileTool(allowed_dir=allowed_dir))
        self.tools.register(ListDirTool(allowed_dir=allowed_dir))
        
        # Shell tool
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
        ))
        
        # Web tools
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())
        
        # Message tool
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)
        
        # Image generation tools
        from nanobot.agent.tools.image_gen import GenerateImageTool, ImageToImageTool, EditImageTool
        image_tool = GenerateImageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(image_tool)
        self.tools.register(ImageToImageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(EditImageTool(send_callback=self.bus.publish_outbound))
        
        # Crawl4AI tool
        self.tools.register(Crawl4AITool(
            api_url=self.crawler_config.api_url,
            max_result_length=self.crawler_config.max_result_length,
            send_callback=self.bus.publish_outbound
        ))

        # Camofox tool (Stealth Browser)
        try:
            from nanobot.agent.tools.camofox import CamofoxTool
            self.tools.register(CamofoxTool(send_callback=self.bus.publish_outbound))
        except ImportError:
            pass  # Dependencies not installed
        
        # Spawn tool (for subagents)
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
        
        # Cron tool (for scheduling)
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))
    
    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")
        
        while self._running:
            try:
                # Wait for next message
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                
                # Process it
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Send error response
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")
    
    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a single inbound message.
        
        Args:
            msg: The inbound message to process.
        
        Returns:
            The response message, or None if no response needed.
        """
        # Handle system messages (subagent announces)
        # The chat_id contains the original "channel:chat_id" to route back to
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {preview}")
        
        # Handle model switch metadata — per-chat model switch
        if msg.metadata and msg.metadata.get("model_switch"):
            new_model = msg.metadata["model_switch"]
            session_key = msg.session_key
            old_model = self._chat_models.get(session_key, self.model)
            self._chat_models[session_key] = new_model
            logger.info(f"Model switched for {session_key}: {old_model} → {new_model}")
            return None  # Confirmation already sent by Telegram handler
        
        # Load user profile if available
        user_profile = None
        if msg.metadata and msg.metadata.get("user_role") is not None:
            from nanobot.users.models import UserProfile, PermissionLevel
            uid = msg.metadata.get("user_chat_id", msg.chat_id)
            try:
                from nanobot.users.manager import UserManager
                um = UserManager()
                user_profile = um.get(uid)
            except Exception as e:
                logger.debug(f"Could not load user profile: {e}")
        
        # Get or create session
        session = self.sessions.get_or_create(msg.session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)
        
        image_tool = self.tools.get("generate_image")
        if isinstance(image_tool, GenerateImageTool):
            image_tool.set_context(msg.channel, msg.chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(msg.channel, msg.chat_id)

        crawler_tool = self.tools.get("crawler")
        if isinstance(crawler_tool, Crawl4AITool):
            crawler_tool.set_context(msg.channel, msg.chat_id)

        camofox_tool = self.tools.get("camofox")
        if camofox_tool: 
            # CamofoxTool might not be loaded if dependencies missing
            if hasattr(camofox_tool, "set_context"):
                camofox_tool.set_context(msg.channel, msg.chat_id)
        
        # Determine allowed tools based on user role
        tool_defs = self.tools.get_definitions()
        if user_profile:
            allowed = user_profile.allowed_tools()
            if allowed is not None:  # None = unrestricted (Admin)
                tool_defs = [t for t in tool_defs if t["function"]["name"] in allowed]
        
        # Trigger memory consolidation if needed
        if len(session.messages) > self.memory_window:
            asyncio.create_task(self._consolidate_memory(session))
        
        # Build initial messages (use get_history for LLM-formatted messages)
        messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
            user_profile=user_profile,
        )
        
        # Agent loop
        iteration = 0
        final_content = None
        
        # Resolve per-chat model (or fallback to global default)
        effective_model = self._chat_models.get(msg.session_key, self.model)
        logger.debug(f"Using model: {effective_model} for session {msg.session_key}")
        
        # Send initial "thinking" progress
        progress = ProgressMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            status="🤔 Đang suy nghĩ...",
        )
        await self.bus.publish_progress(progress)
        
        accumulated_text = ""
        last_update_time = time.time()
        
        async def stream_chunk_handler(chunk: str):
            nonlocal accumulated_text, last_update_time
            accumulated_text += chunk
            now = time.time()
            # Publish streaming progress every 1.5 seconds to avoid rate limiting
            if now - last_update_time >= 1.5:
                last_update_time = now
                if len(accumulated_text) > 80:
                    await self.bus.publish_progress(ProgressMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        status=accumulated_text + "▌",
                    ))
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # Reset streaming state for each iteration
            accumulated_text = ""
            last_update_time = time.time()
            
            # Call LLM — always stream for faster perceived response
            response = await self.provider.chat(
                messages=messages,
                tools=tool_defs if tool_defs else None,
                model=effective_model,
                stream_callback=stream_chunk_handler
            )
            
            # Handle tool calls
            if response.has_tool_calls:
                # Add assistant message with tool calls
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)  # Must be JSON string
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )
                
                # Execute tools — parallel when multiple, sequential otherwise
                if len(response.tool_calls) == 1:
                    tc = response.tool_calls[0]
                    args_str = json.dumps(tc.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tc.name}({args_str[:200]})")
                    
                    tool_status = self._tool_progress_status(tc.name, tc.arguments)
                    await self.bus.publish_progress(ProgressMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        status=tool_status,
                    ))
                    
                    result = await self.tools.execute(tc.name, tc.arguments)
                    messages = self.context.add_tool_result(
                        messages, tc.id, tc.name, result
                    )
                else:
                    # Parallel execution for multiple tool calls
                    tool_names = [tc.name for tc in response.tool_calls]
                    logger.info(f"Parallel tool calls: {tool_names}")
                    
                    await self.bus.publish_progress(ProgressMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        status=f"🔧 Đang chạy {len(response.tool_calls)} tools song song...",
                    ))
                    
                    async def _exec_tool(tc):
                        return await self.tools.execute(tc.name, tc.arguments)
                    
                    results = await asyncio.gather(
                        *[_exec_tool(tc) for tc in response.tool_calls]
                    )
                    
                    for tc, result in zip(response.tool_calls, results):
                        messages = self.context.add_tool_result(
                            messages, tc.id, tc.name, result
                        )
            else:
                # No tool calls — use the content we already have
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "Xin lỗi, mình gặp sự cố khi xử lý tin nhắn. Bạn thử lại nhé! 🦉"
        
        # Guard against empty/whitespace-only responses
        if not final_content.strip():
            final_content = "Xin lỗi, mình không tạo được câu trả lời cho tin nhắn này. Bạn thử diễn đạt lại hoặc thử lại sau nhé! 🦉"
        
        # Log response preview
        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")
        
        # Save to session
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        # Include effective_model in metadata for display purposes
        out_metadata = dict(msg.metadata or {})
        out_metadata["effective_model"] = effective_model
        out_metadata["edit_progress"] = True  # Tell channel to edit progress message
        
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=out_metadata,
        )
    
    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        
        The chat_id field contains "original_channel:original_chat_id" to route
        the response back to the correct destination.
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # Parse origin from chat_id (format: "channel:chat_id")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # Fallback
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        # Use the origin session for context
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(origin_channel, origin_chat_id)
        
        # Build messages with the announce content
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )
        
        # Agent loop (limited for announce handling)
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )
                
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "Background task completed."
        
        # Save to session (mark as system message in history)
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )



    @staticmethod
    def _tool_progress_status(tool_name: str, args: dict) -> str:
        """Map tool name to user-friendly progress status."""
        status_map = {
            "web_search": "🔍 Đang tìm kiếm web...",
            "web_fetch": "🌐 Đang tải trang web...",
            "crawler": "🕷️ Đang cào dữ liệu web...",
            "exec": "⚙️ Đang thực thi lệnh...",
            "read_file": "📖 Đang đọc file...",
            "write_file": "✍️ Đang ghi file...",
            "edit_file": "✏️ Đang sửa file...",
            "list_directory": "📂 Đang liệt kê thư mục...",
            "generate_image": "🎨 Đang tạo ảnh...",
            "message": "💬 Đang gửi tin nhắn...",
            "spawn": "🚀 Đang khởi tạo tác vụ nền...",
            "cron": "⏰ Đang thiết lập lịch...",
        }
        status = status_map.get(tool_name, f"🔧 Đang dùng {tool_name}...")
        
        # Add context for specific tools
        if tool_name == "web_search" and args.get("query"):
            query = args["query"][:40]
            status = f"🔍 Đang tìm kiếm: {query}..."
        elif tool_name == "exec" and args.get("command"):
            cmd = args["command"][:30]
            status = f"⚙️ Đang chạy: {cmd}..."
        elif tool_name == "crawler" and args.get("url"):
            from urllib.parse import urlparse
            domain = urlparse(args["url"]).netloc[:25]
            status = f"🕷️ Đang cào: {domain}..."
        
        return status

    async def _consolidate_memory(self, session, archive_all: bool = False) -> None:
        """Consolidate old messages into MEMORY.md + HISTORY.md."""
        memory = MemoryStore(self.workspace)

        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info(f"Memory consolidation (archive_all): {len(session.messages)} total messages archived")
        else:
            keep_count = self.memory_window // 2
            if len(session.messages) <= keep_count:
                return

            messages_to_process = len(session.messages) - session.last_consolidated
            if messages_to_process <= 0:
                return

            old_messages = session.messages[session.last_consolidated:-keep_count]
            if not old_messages:
                return
            logger.info(f"Memory consolidation started: {len(session.messages)} total, {len(old_messages)} new to consolidate, {keep_count} keep")

        # Format conversation
        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m.get('tools_used', []))}]" if m.get("tools_used") else ""
            timestamp = m.get('timestamp', '?')[:16]
            lines.append(f"[{timestamp}] {m['role'].upper()}{tools}: {m['content']}")
        conversation = "\n".join(lines)
        
        current_memory = memory.read_long_term()

        prompt = f"""You are a memory consolidation agent. Process this conversation and return a JSON object with exactly two keys:

1. "history_entry": A paragraph (2-5 sentences) summarizing the key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM]. Include enough detail to be useful when found by grep search later.

2. "memory_update": The updated long-term memory content. Add any new facts: user location, preferences, personal info, habits, project context, technical decisions, tools/services used. If nothing new, return the existing content unchanged.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{conversation}

Respond with ONLY valid JSON, no markdown fences."""

        try:
            msgs = [
                {"role": "system", "content": "You are a memory consolidation agent. Respond only with valid JSON."},
                {"role": "user", "content": prompt},
            ]
            
            response = await self.provider.chat(
                messages=msgs,
                model=self.model,
            )
            
            content = response.content or ""
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            result = json.loads(content)

            if entry := result.get("history_entry"):
                memory.append_history(entry)
            
            if update := result.get("memory_update"):
                if update != current_memory:
                    memory.write_long_term(update)

            if archive_all:
                session.last_consolidated = 0
            else:
                session.last_consolidated = len(session.messages) - keep_count
            
            logger.info(f"Memory consolidation done: {len(session.messages)} messages, last_consolidated={session.last_consolidated}")
            self.sessions.save(session)
            
        except Exception as e:
            logger.error(f"Memory consolidation failed: {e}")
    
    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> str:
        """
        Process a message directly (for CLI or cron usage).
        
        Args:
            content: The message content.
            session_key: Session identifier.
            channel: Source channel (for context).
            chat_id: Source chat ID (for context).
        
        Returns:
            The agent's response.
        """
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )
        
        response = await self._process_message(msg)
        return response.content if response else ""
