"""Base class for command modules."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api_client import MCBridgeClient
    from .permission import PermissionChecker


class BaseCommandModule:
    """Base class for all AstrBot command modules.

    Each module groups a set of bot commands that interact with the
    MCServerBridge REST API. Command handlers are dispatched from main.py
    by looking the module up via its ``name``.
    """

    name: str = "base"

    def __init__(self, api_client: "MCBridgeClient", permission: "PermissionChecker"):
        self.api = api_client
        self.permission = permission
