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
