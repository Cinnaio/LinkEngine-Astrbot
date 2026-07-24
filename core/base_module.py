"""Base class for command modules."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api_client import MCBridgeClient
    from .permission import PermissionChecker


class BaseCommandModule(ABC):
    """Base class for all AstrBot command modules.

    Each module provides a set of bot commands that interact with
    a specific MCServerBridge API module.
    """

    name: str = "base"
    required_api_module: str = ""  # MC-side module name; empty = no dependency
    admin_only: bool = False

    def __init__(self, api_client: "MCBridgeClient", permission: "PermissionChecker"):
        self.api = api_client
        self.permission = permission

    @abstractmethod
    def get_handlers(self) -> list:
        """Return list of (command_pattern, handler_func, admin_only) tuples.

        handler_func signature: async def handler(event, args: list[str]) -> str
        Returns the response message string.
        """
        ...

    def is_available(self, active_modules: list[str]) -> bool:
        """Check if this module's required MC-side module is active."""
        if not self.required_api_module:
            return True
        return self.required_api_module in active_modules
