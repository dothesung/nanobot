"""Pydantic models for Playground API requests/responses."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat message request."""
    message: str
    session_id: str = "playground:default"
    model: str | None = None  # Override model for this request


class ChatResponse(BaseModel):
    """Chat message response."""
    response: str
    model: str
    usage: dict = Field(default_factory=dict)


class ModelSwitchRequest(BaseModel):
    """Switch active model."""
    model: str
    provider: str | None = None  # Optional provider name override


class ModelInfo(BaseModel):
    """Model information."""
    id: str
    name: str
    provider: str
    description: str = ""


class ProviderInfo(BaseModel):
    """Provider information."""
    name: str
    display_name: str
    configured: bool
    is_gateway: bool = False
    is_local: bool = False
    models: list[ModelInfo] = Field(default_factory=list)


class PlaygroundConfig(BaseModel):
    """Current playground configuration."""
    current_model: str
    current_provider: str | None = None
    providers: list[ProviderInfo] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 8192


class SessionInfo(BaseModel):
    """Session summary."""
    key: str
    created_at: str | None = None
    updated_at: str | None = None
    message_count: int = 0


# Popular models per provider
POPULAR_MODELS: dict[str, list[dict[str, str]]] = {
    "openrouter": [
        {"id": "anthropic/claude-opus-4-5", "name": "Claude Opus 4.5", "description": "Most capable Claude model"},
        {"id": "anthropic/claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "description": "Fast & capable"},
        {"id": "openai/gpt-4o", "name": "GPT-4o", "description": "OpenAI flagship"},
        {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "description": "Fast & affordable"},
        {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "description": "Google fast model"},
        {"id": "google/gemini-2.5-pro-preview", "name": "Gemini 2.5 Pro", "description": "Google flagship"},
        {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat", "description": "DeepSeek V3"},
        {"id": "deepseek/deepseek-reasoner", "name": "DeepSeek R1", "description": "Reasoning model"},
        {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "description": "Meta open model"},
        {"id": "qwen/qwen-2.5-72b-instruct", "name": "Qwen 2.5 72B", "description": "Alibaba model"},
    ],
    "anthropic": [
        {"id": "claude-opus-4-5", "name": "Claude Opus 4.5", "description": "Most capable"},
        {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "description": "Fast & capable"},
        {"id": "claude-haiku-3-5", "name": "Claude Haiku 3.5", "description": "Fastest"},
    ],
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o", "description": "Flagship"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "description": "Fast & affordable"},
        {"id": "o1", "name": "o1", "description": "Reasoning model"},
        {"id": "o3-mini", "name": "o3 Mini", "description": "Fast reasoning"},
    ],
    "deepseek": [
        {"id": "deepseek-chat", "name": "DeepSeek Chat", "description": "V3 general chat"},
        {"id": "deepseek-reasoner", "name": "DeepSeek R1", "description": "Reasoning model"},
    ],
    "gemini": [
        {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "description": "Fast"},
        {"id": "gemini-2.5-pro-preview-06-05", "name": "Gemini 2.5 Pro", "description": "Most capable"},
    ],
    "groq": [
        {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "description": "Fast inference"},
        {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "description": "MoE model"},
    ],
    "dashscope": [
        {"id": "qwen-max", "name": "Qwen Max", "description": "Most capable Qwen"},
        {"id": "qwen-plus", "name": "Qwen Plus", "description": "Balanced"},
        {"id": "qwen-turbo", "name": "Qwen Turbo", "description": "Fast"},
    ],
    "moonshot": [
        {"id": "moonshot-v1-128k", "name": "Moonshot v1 128K", "description": "Long context"},
        {"id": "moonshot-v1-32k", "name": "Moonshot v1 32K", "description": "Standard context"},
    ],
    "zhipu": [
        {"id": "glm-4-plus", "name": "GLM-4 Plus", "description": "Zhipu flagship"},
        {"id": "glm-4-flash", "name": "GLM-4 Flash", "description": "Fast"},
    ],
    "vllm": [
        {"id": "meta-llama/Llama-3.1-8B-Instruct", "name": "Llama 3.1 8B", "description": "Local model"},
    ],
    "genplus": [
        {"id": "genplus/gemini", "name": "GenPlus Gemini", "description": "GenPlus Media AI"},
    ],
}
