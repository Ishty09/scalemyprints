"""
Structured logging with structlog.

All logs are emitted as JSON in production (grep-friendly) and as
human-readable colored text in development.

Usage:
    from scalemyprints.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("user_signed_up", user_id=user.id, email=user.email)
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from scalemyprints.core.config import Environment, LogLevel, get_settings


def _drop_color_message_key(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Remove the `color_message` key from uvicorn's logger to avoid noise."""
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog + stdlib logging.

    Must be called once at app startup, before any log calls.
    """
    settings = get_settings()
    level = getattr(logging, settings.worker_log_level.value, logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _drop_color_message_key,
    ]

    # Dev: pretty console. Prod: JSON lines.
    if settings.environment in (Environment.DEVELOPMENT, Environment.TEST):
        renderer: Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # Quiet down noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a logger instance — wraps structlog.get_logger for convenience."""
    return structlog.get_logger(name)


def bind_request_context(**kwargs: Any) -> None:
    """
    Bind context variables that will appear in all subsequent logs
    within the same async task (request_id, user_id, etc.).
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_request_context() -> None:
    """Clear bound context — call at end of request."""
    structlog.contextvars.clear_contextvars()


__all__ = [
    "LogLevel",
    "bind_request_context",
    "clear_request_context",
    "configure_logging",
    "get_logger",
]
