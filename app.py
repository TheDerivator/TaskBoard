"""ASGI entrypoint (`uvicorn app:app`). The application itself lives in the `taskboard` package."""

from taskboard.web import create_app

app = create_app()
