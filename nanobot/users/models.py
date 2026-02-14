"""User profile and permission models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


class PermissionLevel(IntEnum):
    """Permission levels for bot access.

    GUEST  (0) — basic chat only, no tools, rate-limited.
    USER   (1) — chat + most tools (web search, image gen, etc.).
    ADMIN  (2) — full access + user management commands.
    """

    GUEST = 0
    USER = 1
    ADMIN = 2


# Tools allowed per permission level.
# Admin has no restrictions (all tools).
TOOLS_BY_LEVEL: dict[PermissionLevel, set[str]] = {
    PermissionLevel.GUEST: set(),  # no tools
    PermissionLevel.USER: {
        "read_file",
        "write_file",
        "list_directory",
        "web_search",
        "web_fetch",
        "crawl4ai",
        "generate_image",
        "message",
    },
    PermissionLevel.ADMIN: set(),  # empty = unrestricted
}


@dataclass
class UserProfile:
    """Per-user profile stored on disk."""

    chat_id: str
    name: str = ""
    role: PermissionLevel = PermissionLevel.GUEST
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    daily_limit: int = 20  # messages per day for guests
    usage_today: int = 0
    usage_date: str = ""  # YYYY-MM-DD of last usage count
    preferences: dict = field(default_factory=dict)

    # ----- helpers -----

    def to_dict(self) -> dict:
        return {
            "chat_id": self.chat_id,
            "name": self.name,
            "role": int(self.role),
            "created_at": self.created_at,
            "daily_limit": self.daily_limit,
            "usage_today": self.usage_today,
            "usage_date": self.usage_date,
            "preferences": self.preferences,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserProfile":
        return cls(
            chat_id=data["chat_id"],
            name=data.get("name", ""),
            role=PermissionLevel(data.get("role", 0)),
            created_at=data.get("created_at", datetime.now().isoformat()),
            daily_limit=data.get("daily_limit", 20),
            usage_today=data.get("usage_today", 0),
            usage_date=data.get("usage_date", ""),
            preferences=data.get("preferences", {}),
        )

    def allowed_tools(self) -> set[str] | None:
        """Return the set of allowed tool names, or *None* for unrestricted."""
        if self.role == PermissionLevel.ADMIN:
            return None  # everything
        return TOOLS_BY_LEVEL.get(self.role, set())

    def check_rate_limit(self) -> bool:
        """Return True if the user is within their daily quota."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.usage_date != today:
            self.usage_today = 0
            self.usage_date = today

        if self.role == PermissionLevel.ADMIN:
            return True
        if self.role == PermissionLevel.USER:
            return self.usage_today < 200
        # GUEST
        return self.usage_today < self.daily_limit

    def record_usage(self) -> None:
        """Increment usage counter."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.usage_date != today:
            self.usage_today = 0
            self.usage_date = today
        self.usage_today += 1
