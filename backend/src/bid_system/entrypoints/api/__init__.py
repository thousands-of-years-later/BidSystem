"""FastAPI application entrypoint."""

from bid_system.entrypoints.api.app import create_app

__all__ = ["create_app"]
