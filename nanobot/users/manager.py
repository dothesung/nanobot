"""User manager — CRUD for user profiles and permissions."""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.users.models import PermissionLevel, UserProfile
from nanobot.utils.helpers import ensure_dir


class UserManager:
    """Manage per-user profiles, permissions, and memory paths.

    Data layout under ``~/.nanobot/users/``:
    ::

        _config.json          # owner_chat_ids + defaults
        {chat_id}/
            profile.json      # UserProfile
            memory.md          # per-user long-term memory
    """

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = ensure_dir(data_dir or Path.home() / ".nanobot" / "users")
        self._config_path = self.data_dir / "_config.json"
        self._cache: dict[str, UserProfile] = {}

        # Load system config
        self._sys_config = self._load_sys_config()

    # ------------------------------------------------------------------
    # System config (owner list, defaults)
    # ------------------------------------------------------------------

    def _load_sys_config(self) -> dict[str, Any]:
        if self._config_path.exists():
            try:
                return json.loads(self._config_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to read users config: {e}")
        return {
            "owner_chat_ids": [],
            "default_role": "guest",
            "guest_daily_limit": 20,
            "auto_create_guest": True,
        }

    def _save_sys_config(self) -> None:
        self._config_path.write_text(
            json.dumps(self._sys_config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @property
    def owner_ids(self) -> list[str]:
        return [str(x) for x in self._sys_config.get("owner_chat_ids", [])]

    def add_owner(self, chat_id: str) -> None:
        ids = self.owner_ids
        if chat_id not in ids:
            ids.append(chat_id)
            self._sys_config["owner_chat_ids"] = ids
            self._save_sys_config()
        # Ensure profile is ADMIN
        profile = self.get_or_create(chat_id)
        if profile.role != PermissionLevel.ADMIN:
            profile.role = PermissionLevel.ADMIN
            self.save(profile)

    # ------------------------------------------------------------------
    # Profile CRUD
    # ------------------------------------------------------------------

    def _profile_dir(self, chat_id: str) -> Path:
        return ensure_dir(self.data_dir / str(chat_id))

    def _profile_path(self, chat_id: str) -> Path:
        return self._profile_dir(chat_id) / "profile.json"

    def get(self, chat_id: str) -> UserProfile | None:
        """Get a user profile, or None if not found."""
        chat_id = str(chat_id)

        if chat_id in self._cache:
            return self._cache[chat_id]

        path = self._profile_path(chat_id)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = UserProfile.from_dict(data)

            # owners are always admin
            if chat_id in self.owner_ids:
                profile.role = PermissionLevel.ADMIN

            self._cache[chat_id] = profile
            return profile
        except Exception as e:
            logger.warning(f"Failed to load profile for {chat_id}: {e}")
            return None

    def get_or_create(self, chat_id: str, name: str = "") -> UserProfile:
        """Get an existing profile or create a new one."""
        chat_id = str(chat_id)
        profile = self.get(chat_id)
        if profile:
            # Update name if provided and empty
            if name and not profile.name:
                profile.name = name
                self.save(profile)
            return profile

        # Determine initial role
        if chat_id in self.owner_ids:
            role = PermissionLevel.ADMIN
        else:
            default = self._sys_config.get("default_role", "guest")
            role = PermissionLevel.USER if default == "user" else PermissionLevel.GUEST

        profile = UserProfile(
            chat_id=chat_id,
            name=name,
            role=role,
            daily_limit=self._sys_config.get("guest_daily_limit", 20),
        )
        self.save(profile)
        logger.info(f"Created user profile: {chat_id} ({name}) role={role.name}")
        return profile

    def save(self, profile: UserProfile) -> None:
        """Persist a profile to disk."""
        path = self._profile_path(profile.chat_id)
        path.write_text(
            json.dumps(profile.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._cache[profile.chat_id] = profile

    def set_role(self, chat_id: str, role: PermissionLevel) -> UserProfile | None:
        """Change a user's permission level. Returns the updated profile."""
        chat_id = str(chat_id)

        # Cannot demote owners
        if chat_id in self.owner_ids and role != PermissionLevel.ADMIN:
            logger.warning(f"Cannot demote owner {chat_id}")
            return self.get(chat_id)

        profile = self.get_or_create(chat_id)
        profile.role = role
        self.save(profile)
        logger.info(f"Role changed: {chat_id} → {role.name}")
        return profile

    def list_users(self) -> list[UserProfile]:
        """List all registered users."""
        users: list[UserProfile] = []
        for child in sorted(self.data_dir.iterdir()):
            if child.is_dir() and (child / "profile.json").exists():
                profile = self.get(child.name)
                if profile:
                    users.append(profile)
        return users

    def delete(self, chat_id: str) -> bool:
        """Remove a user profile. Cannot delete owners."""
        chat_id = str(chat_id)
        if chat_id in self.owner_ids:
            return False

        profile_dir = self.data_dir / chat_id
        if profile_dir.exists():
            import shutil
            shutil.rmtree(profile_dir)
            self._cache.pop(chat_id, None)
            logger.info(f"Deleted user profile: {chat_id}")
            return True
        return False

    # ------------------------------------------------------------------
    # Per-user memory
    # ------------------------------------------------------------------

    def get_user_memory_path(self, chat_id: str) -> Path:
        """Get the per-user memory file path."""
        return self._profile_dir(str(chat_id)) / "memory.md"

    def read_user_memory(self, chat_id: str) -> str:
        """Read per-user long-term memory."""
        path = self.get_user_memory_path(chat_id)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def write_user_memory(self, chat_id: str, content: str) -> None:
        """Write per-user long-term memory."""
        path = self.get_user_memory_path(chat_id)
        path.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Access checks
    # ------------------------------------------------------------------

    def check_access(self, chat_id: str) -> tuple[bool, str]:
        """Check if a user can access the bot.

        Returns:
            (allowed, reason) tuple.
        """
        chat_id = str(chat_id)
        profile = self.get(chat_id)

        if profile is None:
            if self._sys_config.get("auto_create_guest", True):
                return True, "auto_guest"
            return False, "not_registered"

        if not profile.check_rate_limit():
            return False, "rate_limited"

        return True, "ok"
