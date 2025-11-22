"""MCP (Model Context Protocol) server for radarr-manager.

Provides AI agent integration via structured tools for movie management.
"""

from radarr_manager.mcp.server import create_mcp_server

__all__ = ["create_mcp_server"]
