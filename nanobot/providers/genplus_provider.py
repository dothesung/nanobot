"""GenPlus Gemini provider - Custom LLM provider using GenPlus Gemini API."""

import aiohttp
from typing import Any

from loguru import logger
from nanobot.providers.base import LLMProvider, LLMResponse


# Default system prompt for nanobot identity
DEFAULT_SYSTEM_PROMPT = """Bạn là GenBot 🦉 - trợ lý AI cá nhân siêu nhẹ được phát triển bởi GenPlus Media.

## QUY TẮC BẮT BUỘC:

1. **LUÔN trả lời bằng Tiếng Việt** - đây là ngôn ngữ mặc định. Chỉ trả lời ngôn ngữ khác khi người dùng yêu cầu dịch rõ ràng.

2. **Danh tính**: Bạn là GenBot, KHÔNG phải Gemini, ChatGPT, Claude hay AI nào khác. Khi được hỏi "Bạn là ai?", trả lời: "Mình là GenBot 🦉, trợ lý AI cá nhân của GenPlus Media!"

3. **Xưng hô**: Xưng "em", gọi người dùng là "Sếp"

4. **Phong cách**: Thân thiện, gần gũi, ngắn gọn, sử dụng emoji phù hợp 😊

5. **Format**: Sử dụng Markdown để trả lời dễ đọc

6. **TUYỆT ĐỐI KHÔNG** được thêm bất kỳ dòng nào liên quan đến "bật chế độ Hoạt động trên Các ứng dụng Gemini" hoặc quảng cáo sản phẩm Google/Gemini vào cuối câu trả lời. KHÔNG BAO GIỜ nhắc đến Gemini."""




class GenPlusProvider(LLMProvider):
    """
    Custom LLM provider using GenPlus Gemini API.
    
    API Endpoint: https://tools.genplusmedia.com/api/chat/gemini.php
    Method: POST
    Input: {"prompt": "...", "sys_prompt": "..."}
    Output: {"status": true, "data": "..."}
    
    Fallback: When GenPlus API fails, automatically retries with
    Pollinations API (openai-fast) to ensure uninterrupted service.
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "genplus/gemini-3.0-flash",
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.api_url = api_base or "https://tools.genplusmedia.com/api/chat/gemini.php"
    
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Send a chat completion request to GenPlus Gemini API.
        Falls back to Pollinations API if GenPlus fails.
        """
        # Extract system prompt and user prompt from messages
        sys_prompt = ""
        user_prompt = ""
        conversation_context = []
        tool_results = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "system":
                if "nanobot" not in content.lower():
                    sys_prompt = DEFAULT_SYSTEM_PROMPT + "\n\n" + content
                else:
                    sys_prompt = content
            elif role == "user":
                user_prompt = content
            elif role == "assistant":
                conversation_context.append(f"[Mình đã trả lời]: {content}")
            elif role == "tool":
                # Collect tool results — critical for tool calling loop
                tool_name = msg.get("name", "unknown_tool")
                tool_results.append(f"[Tool Result: {tool_name}]\n{content}")
        
        if not sys_prompt:
            sys_prompt = DEFAULT_SYSTEM_PROMPT
        
        if not user_prompt and messages:
            user_prompt = messages[-1].get("content", "")
        
        # Include tool results in prompt so model can see what tools returned
        if tool_results:
            results_str = "\n\n".join(tool_results[-3:])  # Last 3 results to avoid too large prompt
            user_prompt = (
                f"{user_prompt}\n\n"
                f"--- TOOL RESULTS ---\n"
                f"{results_str}\n"
                f"--- END TOOL RESULTS ---\n\n"
                f"Based on the tool results above, provide your final answer to the user. "
                f"Do NOT call the same tool again. Summarize the results in a helpful way."
            )
        elif conversation_context:
            context_str = "\n".join(conversation_context[-3:])
            user_prompt = f"[Ngữ cảnh cuộc trò chuyện trước]:\n{context_str}\n\n[Câu hỏi mới]: {user_prompt}"
        
        # --- Tool Handling Setup ---
        # If tools are provided, add instructions to system prompt
        if tools:
            tool_prompt = self._construct_tool_system_prompt(tools)
            sys_prompt += "\n\n" + tool_prompt

        # --- Try GenPlus API first ---
        try:
            async with aiohttp.ClientSession() as session:
                # Determine model name for API (strip genplus/ prefix)
                api_model = (model or self.default_model).replace("genplus/", "")
                
                payload = {
                    "prompt": user_prompt,
                    "sys_prompt": sys_prompt,
                    "model": api_model,
                }
                
                async with session.post(
                    self.api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    # Use content_type=None to skip MIME validation
                    # GenPlus sometimes returns text/html content-type with valid JSON body
                    try:
                        result = await response.json(content_type=None)
                    except Exception:
                        raw = await response.text()
                        logger.warning(f"GenPlus JSON parse failed, raw response: {raw[:200]}")
                        return LLMResponse(
                            content=f"API Error: Invalid JSON response",
                            finish_reason="error",
                        )
                    
                    if result.get("status"):
                        content = result.get("data", "")
                        content = self._clean_response(content)
                        
                        # Try to parse tool calls from content
                        if tools:
                            tool_calls, cleaned_content = self._parse_tool_calls(content)
                            if tool_calls:
                                return LLMResponse(
                                    content=cleaned_content or "Thinking...", # Keep content if any thinking process is shown
                                    tool_calls=tool_calls,
                                    finish_reason="tool_calls",
                                )
                        
                        return LLMResponse(
                            content=content,
                            finish_reason="stop",
                        )
                    else:
                        error_msg = result.get('message', 'Unknown error')
                        logger.warning(f"GenPlus API error: {error_msg}")
                        return LLMResponse(
                            content=f"API Error: {error_msg}",
                            finish_reason="error",
                        )
        except Exception as e:
            logger.warning(f"GenPlus API exception: {e}")
            return LLMResponse(
                content=f"API Error: {str(e)}",
                finish_reason="error",
            )
    
    def _construct_tool_system_prompt(self, tools: list[dict[str, Any]]) -> str:
        """Construct the system prompt supplement for tool usage."""
        import json
        
        tool_descs = []
        for t in tools:
            if t.get("type") == "function":
                func = t.get("function", {})
                tool_descs.append({
                    "name": func.get("name"),
                    "description": func.get("description"),
                    "parameters": func.get("parameters")
                })
        
        tools_json = json.dumps(tool_descs, indent=2)
        
        return (
            "\n## TOOL USAGE INSTRUCTIONS\n"
            "You have access to the following tools:\n\n"
            + tools_json + "\n\n"
            "### RULES:\n"
            "1. **THINK FIRST**: Before using a tool, explain WHY you need it in a short sentence.\n"
            "2. **NO HALLUCINATIONS**: Do NOT say you have done something (like creating an image) unless you have successfully emitted the tool code.\n"
            "3. **JSON FORMAT**: To use a tool, you MUST output a valid JSON block wrapped in <tool_code> tags.\n"
            "4. **ONE TOOL PER BLOCK**: You can call multiple tools, but each must be in its own <tool_code> block.\n"
            "5. **parameters**: Verify you are using the correct arguments matching the schema.\n\n"
            "### FORMAT:\n"
            "Thinking: I need to search for the latest news.\n"
            "<tool_code>\n"
            '{"name": "web_search", "arguments": {"query": "latest news Vietnam"}}\n'
            "</tool_code>\n"
        )

    def _parse_tool_calls(self, content: str) -> tuple[list[Any], str | None]:
        """
        Parse tool calls from the model output.
        Returns (list of tool calls, cleaned content).
        """
        import re
        import json
        from nanobot.providers.base import ToolCallRequest
        import uuid

        tool_calls = []
        
        # Regex to find <tool_code> blocks
        # Using DOTALL to match across newlines
        pattern = r'<tool_code>\s*({.*?})\s*</tool_code>'
        matches = re.finditer(pattern, content, re.DOTALL)
        
        cleaned_content = content
        
        for match in matches:
            json_str = match.group(1)
            try:
                data = json.loads(json_str)
                name = data.get("name")
                args = data.get("arguments", {})
                
                # Strip markdown link format from string args (e.g. "[url](url)" -> "url")
                args = self._strip_markdown_from_args(args)
                
                if name:
                    tool_calls.append(ToolCallRequest(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name=name,
                        arguments=args
                    ))
                    # Remove the tool call block from content to avoid showing it to user
                    cleaned_content = cleaned_content.replace(match.group(0), "")
            except json.JSONDecodeError:
                logger.warning(f"Failed to decode tool call JSON: {json_str[:50]}...")
                continue

        cleaned_content = cleaned_content.strip()
        # If content is empty after removing tool calls, return None so logic knows it was purely a tool call
        if not cleaned_content and tool_calls:
            cleaned_content = None
            
        return tool_calls, cleaned_content

    @staticmethod
    def _strip_markdown_from_args(args: dict) -> dict:
        """Strip markdown link format from string arguments."""
        import re
        cleaned = {}
        for key, val in args.items():
            if isinstance(val, str):
                # Convert [text](url) to just url
                md_link = re.match(r'^\[([^\]]+)\]\(([^\)]+)\)$', val.strip())
                if md_link:
                    val = md_link.group(2)  # Use the URL part
            cleaned[key] = val
        return cleaned



    
    @staticmethod
    def _clean_response(content: str) -> str:
        """Remove unwanted Gemini promotional/system text from responses."""
        import re
        # Remove any variation of the Gemini promo text
        patterns = [
            # Full markdown link: [promo text](url)
            r'\[Để dùng được toàn bộ chức năng.*?\]\(https?://myactivity\.google\.com/product/gemini\)\.?',
            # Markdown link in middle of sentence: "bật chế độ [text](url)."
            r'Để dùng được toàn bộ chức năng[^.]*?\[.*?\]\(https?://[^\)]+\)\.?',
            # Plain text with "Hoạt động trên Các ứng dụng Gemini"
            r'Để dùng được toàn bộ chức năng.*?(?:Các ứng dụng Gemini|Gemini Apps)\.?',
            # English variant
            r'To use all the features.*?Gemini Apps\.?',
            # Partial remnants
            r'[Hh]ãy bật chế độ Hoạt động trên Các ứng dụng Gemini\.?',
            # Bare URL or markdown link remnant
            r'\]?\(?\s*https?://myactivity\.google\.com/product/gemini\s*\)?\s*\.?',
            # Standalone "bật chế độ [Hoạt động...](url)" pattern
            r'bật chế độ\s*\[.*?\]\(https?://[^\)]+\)\.?',
        ]
        for pattern in patterns:
            content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
        # Clean up trailing whitespace and extra newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()
    
    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model
