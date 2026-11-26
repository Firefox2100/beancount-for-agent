"""A small server-rendered interface for what only the user does: approving proposals and
maintaining accounts and the profile. It is another adapter on the same services as the API."""

from beancount_mcp.ui.router import install

__all__ = ["install"]
