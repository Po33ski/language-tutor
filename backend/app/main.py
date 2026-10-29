import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models import BaseChatModel

from app.agent.graph import build_model, build_tutor_agent
from app.agent.summarizer import Summarizer, build_summarizer
from app.agent.wrapup import end_stale_lessons
from app.api import health, lessons, profiles
from app.config import Settings, get_settings
from app.storage.persistence import open_persistence

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    model: BaseChatModel | None = None,
    summarizer: Summarizer | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own settings (temp data dir) and fakes for the LLM."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with open_persistence(settings) as persistence:
            app.state.settings = settings
            app.state.persistence = persistence
            app.state.tutor = build_tutor_agent(
                model or build_model(settings), persistence.checkpointer, persistence.store
            )
            app.state.summarizer = summarizer or build_summarizer(settings)
            app.state.lesson_locks = defaultdict(asyncio.Lock)
            # Summarize lessons left open last time, without delaying startup.
            sweep = asyncio.create_task(
                _end_stale_lessons(app, timedelta(hours=settings.stale_lesson_hours))
            )
            yield
            sweep.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweep

    app = FastAPI(title="Language Tutor API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (health.router, profiles.router, lessons.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()


async def _end_stale_lessons(app: FastAPI, max_idle: timedelta) -> None:
    try:
        ended = await end_stale_lessons(
            app.state.persistence.store,
            app.state.tutor,
            app.state.summarizer,
            app.state.lesson_locks,
            max_idle,
        )
        if ended:
            logger.info("Ended %d stale lesson(s)", ended)
    except Exception:
        logger.exception("Stale lesson sweep failed")
