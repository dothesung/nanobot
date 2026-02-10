"""Resilient Provider — failover chain with circuit breaker pattern."""

import time
from typing import Any, Callable, Awaitable

from loguru import logger
from nanobot.providers.base import LLMProvider, LLMResponse


class ProviderHealth:
    """Track health of a single provider using circuit breaker pattern."""

    def __init__(self, name: str, max_failures: int = 3, cooldown: int = 60):
        self.name = name
        self.max_failures = max_failures
        self.cooldown = cooldown
        self.failures = 0
        self.last_failure_time = 0.0
        self.total_calls = 0
        self.total_errors = 0

    @property
    def is_open(self) -> bool:
        """True if circuit is open (provider should be skipped)."""
        if self.failures < self.max_failures:
            return False
        # Check if cooldown has elapsed — allow a retry
        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.cooldown:
            logger.info(f"⚡ Circuit half-open for {self.name} — retrying after {elapsed:.0f}s cooldown")
            return False
        return True

    def record_success(self) -> None:
        """Reset failure count on success."""
        if self.failures > 0:
            logger.info(f"✅ {self.name} recovered — resetting circuit breaker")
        self.failures = 0
        self.total_calls += 1

    def record_failure(self, error: str = "") -> None:
        """Record a failure. Opens circuit after max_failures."""
        self.failures += 1
        self.total_errors += 1
        self.total_calls += 1
        self.last_failure_time = time.time()
        logger.warning(
            f"⚠️ {self.name} failure {self.failures}/{self.max_failures}: {error[:100]}"
        )
        if self.failures >= self.max_failures:
            logger.error(
                f"🔴 Circuit OPEN for {self.name} — skipping for {self.cooldown}s"
            )

    def status_dict(self) -> dict:
        """Return health status as dict."""
        return {
            "name": self.name,
            "healthy": not self.is_open,
            "failures": self.failures,
            "total_calls": self.total_calls,
            "total_errors": self.total_errors,
        }


# Type alias for notify callback
NotifyCallback = Callable[[str, str], Awaitable[None]] | None


class ResilientProvider(LLMProvider):
    """
    Failover chain provider with circuit breaker.
    
    Wraps multiple LLMProviders and tries them in order.
    If a provider fails, it moves to the next one.
    After max_failures consecutive failures, a provider is
    temporarily skipped (circuit breaker pattern).
    """

    def __init__(
        self,
        chain: list[tuple[str, LLMProvider]],
        max_failures: int = 3,
        cooldown_seconds: int = 60,
        notify_on_failover: bool = True,
    ):
        """
        Args:
            chain: List of (name, provider) tuples in priority order.
            max_failures: Failures before circuit opens for a provider.
            cooldown_seconds: Seconds before retrying a failed provider.
            notify_on_failover: Whether to log/notify on provider switch.
        """
        super().__init__()
        self.chain = chain
        self.notify_on_failover = notify_on_failover
        self._health: dict[str, ProviderHealth] = {}
        self._current_provider_name: str = chain[0][0] if chain else "unknown"

        for name, _ in chain:
            self._health[name] = ProviderHealth(name, max_failures, cooldown_seconds)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Try each provider in the chain until one succeeds.
        
        Returns the first successful response, or an error message
        if all providers fail.
        """
        errors: list[str] = []
        attempted = 0

        for name, provider in self.chain:
            health = self._health[name]

            # Skip providers with open circuit
            if health.is_open:
                logger.debug(f"⏭️ Skipping {name} — circuit open")
                continue

            attempted += 1

            try:
                response = await provider.chat(
                    messages=messages,
                    tools=tools,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                # Check for error responses
                if response.finish_reason == "error":
                    error_msg = response.content or "Unknown error"
                    health.record_failure(error_msg)
                    errors.append(f"{name}: {error_msg}")

                    if self.notify_on_failover and name == self._current_provider_name:
                        logger.warning(f"🔄 Failover: {name} → next provider")
                    continue

                # Success!
                health.record_success()

                # Log provider switch if different from previous
                if name != self._current_provider_name:
                    logger.info(
                        f"🔄 Provider switched: {self._current_provider_name} → {name}"
                    )
                    self._current_provider_name = name

                return response

            except Exception as e:
                error_msg = str(e)
                health.record_failure(error_msg)
                errors.append(f"{name}: {error_msg}")

                if self.notify_on_failover:
                    logger.warning(f"🔄 Failover: {name} failed ({error_msg[:80]}) → next")
                continue

        # All providers failed
        error_summary = "\n".join(f"  • {e}" for e in errors[-3:])
        logger.error(f"❌ All {attempted} providers failed:\n{error_summary}")

        return LLMResponse(
            content=(
                "⚠️ Xin lỗi bạn, tất cả các nhà cung cấp AI đang gặp sự cố. "
                "Vui lòng thử lại sau vài phút nhé! 🐈"
            ),
            finish_reason="error",
        )

    def get_default_model(self) -> str:
        """Return default model from first provider."""
        if self.chain:
            return self.chain[0][1].get_default_model()
        return "unknown"

    @property
    def current_provider(self) -> str:
        """Name of the currently active provider."""
        return self._current_provider_name

    def health_status(self) -> list[dict]:
        """Get health status of all providers in the chain."""
        return [self._health[name].status_dict() for name, _ in self.chain]

    def health_summary(self) -> str:
        """Human-readable health summary."""
        lines = []
        for name, _ in self.chain:
            h = self._health[name]
            icon = "🟢" if not h.is_open else "🔴"
            lines.append(f"{icon} {name}: {h.total_calls} calls, {h.total_errors} errors")
        return "\n".join(lines)
