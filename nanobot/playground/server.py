"""Playground HTTP server — serves chat API + static web UI."""

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"


class PlaygroundServer:
    """
    Lightweight HTTP server for nanobot Playground.

    Provides:
      - REST API for chat, config, models, sessions
      - Static file serving for the web UI
      - Runtime model switching without restart
    """

    def __init__(
        self,
        config: Any,
        host: str = "localhost",
        port: int = 8080,
    ):
        self.config = config
        self.host = host
        self.port = port

        # Lazy-created on start
        self._agent = None
        self._provider = None
        self._bus = None
        self._session_manager = None
        self._current_model = config.agents.defaults.model
        self._current_temperature = config.agents.defaults.temperature
        self._current_max_tokens = config.agents.defaults.max_tokens
        self._custom_api_base = None
        self._custom_api_key = None

    def _make_provider(self, model: str | None = None):
        """Create LLM provider for a given model."""
        from nanobot.providers.litellm_provider import LiteLLMProvider

        target_model = model or self._current_model

        if target_model.lower().startswith("genplus"):
            from nanobot.providers.genplus_provider import GenPlusProvider
            from nanobot.providers.direct_provider import DirectProvider
            from nanobot.providers.resilient_provider import ResilientProvider
            
            p = self.config.providers.genplus
            
            # Build failover chain
            chain = [
                ("GenPlus", GenPlusProvider(
                    api_key=p.api_key if p else None,
                    api_base=p.api_base or "https://tools.genplusmedia.com/api/chat/gemini.php",
                    default_model=target_model,
                )),
                ("Pollinations", DirectProvider(
                    api_key="plln_sk_CtcGj14XKaIKRXm8XeqguwQiQxmZ6a6tHAMMpdrhLTxiIomsp1Qv9U9nS6HfBviF",
                    api_base="https://gen.pollinations.ai/v1",
                    default_model="gemini-fast",
                )),
            ]
            
            # Add Groq if configured
            groq_cfg = self.config.providers.groq
            if groq_cfg and groq_cfg.api_key:
                chain.append(("Groq", DirectProvider(
                    api_key=groq_cfg.api_key,
                    api_base="https://api.groq.com/openai/v1",
                    default_model="llama-3.3-70b-versatile",
                )))
            
            return ResilientProvider(chain=chain, max_failures=3, cooldown_seconds=60)

        # Custom endpoint override — bypass LiteLLM, direct HTTP calls
        if self._custom_api_base:
            from nanobot.providers.direct_provider import DirectProvider
            return DirectProvider(
                api_key=self._custom_api_key,
                api_base=self._custom_api_base,
                default_model=target_model,
            )

        p = self.config.get_provider(target_model)
        return LiteLLMProvider(
            api_key=p.api_key if p else None,
            api_base=self.config.get_api_base(target_model),
            default_model=target_model,
            extra_headers=p.extra_headers if p else None,
            provider_name=self.config.get_provider_name(target_model),
        )

    def _make_agent(self):
        """Create/recreate agent loop with current provider."""
        from nanobot.bus.queue import MessageBus
        from nanobot.agent.loop import AgentLoop
        from nanobot.session.manager import SessionManager

        if self._bus is None:
            self._bus = MessageBus()
        if self._session_manager is None:
            self._session_manager = SessionManager(self.config.workspace_path)

        self._provider = self._make_provider()
        self._agent = AgentLoop(
            bus=self._bus,
            provider=self._provider,
            workspace=self.config.workspace_path,
            model=self._current_model,
            max_iterations=self.config.agents.defaults.max_tool_iterations,
            brave_api_key=self.config.tools.web.search.api_key or None,
            exec_config=self.config.tools.exec,
            restrict_to_workspace=self.config.tools.restrict_to_workspace,
            session_manager=self._session_manager,
        )

    # ------------------------------------------------------------------
    # API handlers
    # ------------------------------------------------------------------

    async def _handle_api_config(self) -> dict:
        """GET /api/config — return current config."""
        from nanobot.providers.registry import PROVIDERS
        from nanobot.playground.models import POPULAR_MODELS

        providers = []
        for spec in PROVIDERS:
            p = getattr(self.config.providers, spec.name, None)
            if p is None:
                continue
            configured = bool(p.api_key) or (spec.is_local and bool(p.api_base))
            models_list = [
                {"id": m["id"], "name": m["name"], "provider": spec.name, "description": m.get("description", "")}
                for m in POPULAR_MODELS.get(spec.name, [])
            ]
            providers.append({
                "name": spec.name,
                "displayName": spec.display_name,
                "configured": configured,
                "isGateway": spec.is_gateway,
                "isLocal": spec.is_local,
                "models": models_list,
            })

        return {
            "currentModel": self._current_model,
            "currentProvider": self.config.get_provider_name(self._current_model),
            "temperature": self._current_temperature,
            "maxTokens": self._current_max_tokens,
            "providers": providers,
        }

    async def _handle_api_chat(self, data: dict) -> dict:
        """POST /api/chat — send message to agent."""
        message = data.get("message", "").strip()
        if not message:
            return {"error": "Empty message"}

        session_id = data.get("sessionId", "playground:default")
        model_override = data.get("model")

        # Only switch model if NOT using custom endpoint
        if not self._custom_api_base:
            if model_override and model_override != self._current_model:
                self._current_model = model_override
                self._make_agent()

        if self._agent is None:
            self._make_agent()

        response = await self._agent.process_direct(
            content=message,
            session_key=session_id,
            channel="playground",
            chat_id="web",
        )

        return {
            "response": response or "",
            "model": self._current_model,
        }

    async def _handle_api_model_switch(self, data: dict) -> dict:
        """POST /api/model — switch model runtime."""
        new_model = data.get("model", "").strip()
        if not new_model:
            return {"error": "No model specified"}

        self._current_model = new_model
        if data.get("temperature") is not None:
            self._current_temperature = float(data["temperature"])
        if data.get("maxTokens") is not None:
            self._current_max_tokens = int(data["maxTokens"])

        # Clear custom endpoint when switching to built-in provider
        self._custom_api_base = None
        self._custom_api_key = None

        self._make_agent()

        return {
            "success": True,
            "model": self._current_model,
            "provider": self.config.get_provider_name(self._current_model),
        }

    async def _handle_api_sessions(self) -> dict:
        """GET /api/sessions — list sessions."""
        if self._session_manager is None:
            return {"sessions": []}

        sessions = self._session_manager.list_sessions()
        return {
            "sessions": [
                {
                    "key": s["key"],
                    "createdAt": s.get("created_at"),
                    "updatedAt": s.get("updated_at"),
                }
                for s in sessions
                if s["key"].startswith("playground:")
            ]
        }

    async def _handle_api_session_clear(self, data: dict) -> dict:
        """POST /api/sessions/clear — clear a session."""
        session_id = data.get("sessionId", "playground:default")
        if self._session_manager:
            self._session_manager.delete(session_id)
        return {"success": True}

    async def _handle_api_endpoint(self, data: dict) -> dict:
        """POST /api/endpoint — connect a custom endpoint."""
        api_base = data.get("apiBase", "").strip()
        api_key = data.get("apiKey", "").strip()
        model = data.get("model", "").strip()

        if not api_base:
            return {"error": "API Base URL is required"}
        if not model:
            return {"error": "Model name is required"}

        # Remove trailing /v1/chat/completions if present (LiteLLM adds it)
        for suffix in ["/v1/chat/completions", "/v1"]:
            if api_base.endswith(suffix):
                api_base = api_base[: -len(suffix)]
                break

        self._custom_api_base = api_base
        self._custom_api_key = api_key or None
        self._current_model = model
        self._make_agent()

        return {
            "success": True,
            "model": model,
            "provider": "custom",
            "apiBase": api_base,
        }

    # ------------------------------------------------------------------
    # HTTP request handling
    # ------------------------------------------------------------------

    async def _handle_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a single HTTP request."""
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=30)
            if not request_line:
                writer.close()
                return

            request_str = request_line.decode("utf-8", errors="replace").strip()
            parts = request_str.split(" ")
            if len(parts) < 2:
                writer.close()
                return

            method, path = parts[0], parts[1]

            # Read headers
            headers: dict[str, str] = {}
            content_length = 0
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=10)
                decoded = line.decode("utf-8", errors="replace").strip()
                if not decoded:
                    break
                if ":" in decoded:
                    k, v = decoded.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
                    if k.strip().lower() == "content-length":
                        content_length = int(v.strip())

            # Read body
            body = b""
            if content_length > 0:
                body = await asyncio.wait_for(reader.readexactly(content_length), timeout=30)

            # Route
            status, response_body, content_type = await self._route(method, path, body)

            # Send response
            response_bytes = response_body.encode("utf-8") if isinstance(response_body, str) else response_body
            response = (
                f"HTTP/1.1 {status}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(response_bytes)}\r\n"
                f"Access-Control-Allow-Origin: *\r\n"
                f"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                f"Access-Control-Allow-Headers: Content-Type\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            )
            writer.write(response.encode("utf-8"))
            writer.write(response_bytes)
            await writer.drain()

        except Exception as e:
            logger.debug(f"Request error: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _route(self, method: str, path: str, body: bytes) -> tuple[str, str | bytes, str]:
        """Route request to handler. Returns (status, body, content_type)."""

        # CORS preflight
        if method == "OPTIONS":
            return "200 OK", "", "text/plain"

        # Strip query string
        path = path.split("?")[0]

        # API routes
        if path == "/api/config" and method == "GET":
            result = await self._handle_api_config()
            return "200 OK", json.dumps(result), "application/json"

        if path == "/api/chat" and method == "POST":
            data = json.loads(body) if body else {}
            result = await self._handle_api_chat(data)
            status = "200 OK" if "error" not in result else "400 Bad Request"
            return status, json.dumps(result), "application/json"

        if path == "/api/model" and method == "POST":
            data = json.loads(body) if body else {}
            result = await self._handle_api_model_switch(data)
            status = "200 OK" if "error" not in result else "400 Bad Request"
            return status, json.dumps(result), "application/json"

        if path == "/api/sessions" and method == "GET":
            result = await self._handle_api_sessions()
            return "200 OK", json.dumps(result), "application/json"

        if path == "/api/sessions/clear" and method == "POST":
            data = json.loads(body) if body else {}
            result = await self._handle_api_session_clear(data)
            return "200 OK", json.dumps(result), "application/json"

        if path == "/api/endpoint" and method == "POST":
            data = json.loads(body) if body else {}
            result = await self._handle_api_endpoint(data)
            status = "200 OK" if "error" not in result else "400 Bad Request"
            return status, json.dumps(result), "application/json"

        # Static files
        if method == "GET":
            return self._serve_static(path)

        return "404 Not Found", json.dumps({"error": "Not found"}), "application/json"

    def _serve_static(self, path: str) -> tuple[str, str | bytes, str]:
        """Serve static files from the static directory."""
        if path == "/" or path == "":
            path = "/index.html"

        file_path = STATIC_DIR / path.lstrip("/")

        # Security: prevent directory traversal
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(STATIC_DIR.resolve())):
                return "403 Forbidden", "Forbidden", "text/plain"
        except Exception:
            return "403 Forbidden", "Forbidden", "text/plain"

        if not file_path.exists() or not file_path.is_file():
            return "404 Not Found", "Not Found", "text/plain"

        # MIME types
        ext = file_path.suffix.lower()
        mime_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".woff2": "font/woff2",
            ".woff": "font/woff",
        }
        content_type = mime_types.get(ext, "application/octet-stream")

        content = file_path.read_bytes()
        return "200 OK", content, content_type

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    async def start(self):
        """Start the playground server + enabled channels (Telegram, etc.)."""
        import os
        skip_channels = os.environ.get("NANOBOT_CHANNELS__TELEGRAM__ENABLED", "").lower() == "false"

        self._make_agent()

        enabled = []
        if not skip_channels:
            # Start channels (Telegram, etc.) alongside web server
            from nanobot.channels.manager import ChannelManager
            self._channel_manager = ChannelManager(
                self.config, self._bus, session_manager=self._session_manager
            )
            enabled = self._channel_manager.enabled_channels
            if enabled:
                logger.info(f"Channels enabled: {', '.join(enabled)}")
        else:
            logger.info("Channels skipped (standalone playground mode)")

        server = await asyncio.start_server(
            self._handle_request, self.host, self.port
        )

        url = f"http://{self.host}:{self.port}"
        if self.host == "0.0.0.0":
            url = f"http://localhost:{self.port}"

        logger.info(f"Playground running at {url}")

        async with server:
            if enabled:
                # Run web server + agent loop + channels concurrently
                await asyncio.gather(
                    server.serve_forever(),
                    self._agent.run(),
                    self._channel_manager.start_all(),
                )
            else:
                await server.serve_forever()
