"""Web layer: builds the ASGI application (API, static frontend, middleware)."""

from taskboard.web.app_factory import create_app

__all__ = ["create_app"]
