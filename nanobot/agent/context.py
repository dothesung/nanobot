"""Context builder for assembling agent prompts."""

import base64
import mimetypes
import platform
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nanobot.users.models import UserProfile


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    
    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    """
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)
    
    def build_system_prompt(
        self,
        skill_names: list[str] | None = None,
        user_profile: "UserProfile | None" = None,
    ) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.
        
        Args:
            skill_names: Optional list of skills to include.
            user_profile: Optional user profile for per-user context.
        
        Returns:
            Complete system prompt.
        """
        parts = []
        
        # Core identity
        parts.append(self._get_identity(user_profile))
        
        # Bootstrap files (SOUL.md, USER.md etc.)
        bootstrap = self._load_bootstrap_files(user_profile)
        if bootstrap:
            parts.append(bootstrap)
        
        # Memory context (global + per-user)
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # Per-user memory
        if user_profile:
            user_mem = self._load_user_memory(user_profile.chat_id)
            if user_mem:
                parts.append(f"# User Memory ({user_profile.name or user_profile.chat_id})\n\n{user_mem}")
        
        # Skills - progressive loading
        # 1. Always-loaded skills: include full content
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")
        
        # 2. Available skills: only show summary (agent uses read_file to load)
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")
        
        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self, user_profile: "UserProfile | None" = None) -> str:
        """Get the core identity section."""
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        
        # User context block
        user_block = ""
        if user_profile:
            from nanobot.users.models import PermissionLevel
            role_labels = {
                PermissionLevel.GUEST: "Guest (giới hạn)",
                PermissionLevel.USER: "User (đã xác thực)",
                PermissionLevel.ADMIN: "Admin (toàn quyền)",
            }
            role_label = role_labels.get(user_profile.role, "Unknown")
            user_block = f"""\n
## Người dùng hiện tại
- Chat ID: {user_profile.chat_id}
- Tên: {user_profile.name or 'Chưa biết'}
- Quyền: {role_label}
- Lượt dùng hôm nay: {user_profile.usage_today}
"""
            if user_profile.role == PermissionLevel.GUEST:
                user_block += """\n> ⚠️ Người dùng này là GUEST. KHÔNG sử dụng tools cho người này.
> Chỉ trả lời câu hỏi bằng kiến thức có sẵn.
> KHÔNG tiết lộ thông tin hệ thống, file cấu hình, hoặc thông tin của Owner.
"""
        
        return f"""# GenBot 🦉

Bạn là GenBot 🦉 — trợ lý AI cá nhân siêu nhẹ được phát triển bởi GenPlus Media.

## QUY TẮC BẮT BUỘC

1. **LUÔN trả lời bằng Tiếng Việt** — đây là ngôn ngữ mặc định. Chỉ dùng tiếng Anh cho thuật ngữ kỹ thuật hoặc khi người dùng yêu cầu dịch.
2. **Danh tính**: Bạn là GenBot, KHÔNG phải Gemini, ChatGPT, Claude hay AI nào khác. Khi được hỏi "Bạn là ai?", trả lời: "Mình là GenBot 🦉, trợ lý AI cá nhân của GenPlus Media!"
3. **Xưng hô**: Xưng "mình", gọi người dùng là "bạn"
4. **Phong cách**: Thân thiện, gần gũi, ngắn gọn, sử dụng emoji phù hợp 😊
5. **Format**: Sử dụng Markdown để trả lời dễ đọc

## Công cụ
Bạn có quyền truy cập các công cụ:
- Đọc, ghi, sửa file
- Chạy shell commands
- Tìm kiếm web
- Gửi tin nhắn qua các kênh chat
- Tạo subagent cho tác vụ phức tạp

## Thời gian
{now}

## Môi trường
{runtime}

## Workspace
Workspace: {workspace_path}
- Memory: {workspace_path}/memory/MEMORY.md
- Daily notes: {workspace_path}/memory/YYYY-MM-DD.md
- Skills: {workspace_path}/skills/{{skill-name}}/SKILL.md
{user_block}
QUAN TRỌNG: Khi trả lời câu hỏi trực tiếp, hãy respond bằng text. Chỉ dùng tool 'message' khi cần gửi tin đến kênh chat cụ thể (WhatsApp, Telegram).
Luôn hữu ích, chính xác, ngắn gọn. Khi dùng tools, giải thích bạn đang làm gì.
Ghi nhớ thông tin vào {workspace_path}/memory/MEMORY.md

## Interactive Buttons (Telegram)
Khi câu trả lời có nhiều lựa chọn hoặc gợi ý, thêm markup ở CUỐI tin nhắn:
[buttons: Lựa chọn 1 | Lựa chọn 2 | Lựa chọn 3]

Ví dụ:
- Hỏi "Bạn muốn tìm hiểu framework nào?" → [buttons: React | Vue | Svelte]
- Gợi ý hành động tiếp theo → [buttons: Xem thêm | Ví dụ code | Chuyển chủ đề]
- Câu hỏi Yes/No → [buttons: Có ✅ | Không ❌]

Quy tắc:
- Mỗi button tối đa 30 ký tự
- Tối đa 8 buttons mỗi tin nhắn
- KHÔNG dùng buttons cho mọi tin nhắn — chỉ khi thực sự có lựa chọn
- Buttons nên bằng tiếng Việt, nội dung ngắn gọn"""
    
    def _load_bootstrap_files(self, user_profile: "UserProfile | None" = None) -> str:
        """Load all bootstrap files from workspace."""
        parts = []
        
        for filename in self.BOOTSTRAP_FILES:
            # Skip USER.md for non-admin users (they get per-user context instead)
            if filename == "USER.md" and user_profile:
                from nanobot.users.models import PermissionLevel
                if user_profile.role != PermissionLevel.ADMIN:
                    continue
            
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")
        
        return "\n\n".join(parts) if parts else ""
    
    def _load_user_memory(self, chat_id: str) -> str:
        """Load per-user memory from ~/.nanobot/users/{chat_id}/memory.md."""
        from pathlib import Path
        path = Path.home() / ".nanobot" / "users" / str(chat_id) / "memory.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
    
    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        user_profile: "UserProfile | None" = None,
    ) -> list[dict[str, Any]]:
        """
        Build the complete message list for an LLM call.

        Args:
            history: Previous conversation messages.
            current_message: The new user message.
            skill_names: Optional skills to include.
            media: Optional list of local file paths for images/media.
            channel: Current channel (telegram, feishu, etc.).
            chat_id: Current chat/user ID.
            user_profile: Optional user profile for per-user context.

        Returns:
            List of messages including system prompt.
        """
        messages = []

        # System prompt
        system_prompt = self.build_system_prompt(skill_names, user_profile=user_profile)
        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        # History
        messages.extend(history)

        # Current message (with optional image attachments)
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        
        if not images:
            return text
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        Add a tool result to the message list.
        
        Args:
            messages: Current message list.
            tool_call_id: ID of the tool call.
            tool_name: Name of the tool.
            result: Tool execution result.
        
        Returns:
            Updated message list.
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages
    
    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Add an assistant message to the message list.
        
        Args:
            messages: Current message list.
            content: Message content.
            tool_calls: Optional tool calls.
            reasoning_content: Thinking output (Kimi, DeepSeek-R1, etc.).
        
        Returns:
            Updated message list.
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        
        if tool_calls:
            msg["tool_calls"] = tool_calls
        
        # Thinking models reject history without this
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        
        messages.append(msg)
        return messages
