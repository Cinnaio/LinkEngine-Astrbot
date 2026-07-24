"""Permission checker for admin commands."""

import logging

logger = logging.getLogger("astrbot.mcbridge")


class PermissionChecker:
    """Checks if a user has admin permissions based on configured admin list."""

    def __init__(self, admins: list[str]):
        self.admins = set(admins)

    def is_admin(self, user_id: str) -> bool:
        """Check if the user ID is in the admin list."""
        return user_id in self.admins

    def get_player_uuid(self, user_id: str, bindmap: dict[str, str]) -> str | None:
        """Get the MC UUID bound to a user ID from the bindmap."""
        return bindmap.get(user_id)

    def update_admins(self, admins: list[str]):
        """Update the admin list."""
        self.admins = set(admins)
