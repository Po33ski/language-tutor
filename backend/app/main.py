import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models import BaseChatModel

from app.agent.graph import build_model, build_tutor_agent
from app.agent.summarizer import Summarizer, build_summarizer
from app.agent.wrapup import end_stale_lessons
from app.api import auth, health, lessons, profiles, speech
from app.api.security import RateLimiter, require_access_key
from app.config import Settings, get_settings
from app.speech.service import DefaultSpeechService, SpeechService
from app.storage.persistence import open_persistence

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    model: BaseChatModel | None = None,
    summarizer: Summarizer | None = None,
    speech_service: SpeechService | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own settings (temp data dir) and fakes for the models."""
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
            app.state.rate_limiter = (
                RateLimiter(settings.rate_limit_per_minute)
                if settings.rate_limit_per_minute > 0
                else None
            )
            if not settings.access_key:
                logger.warning("ACCESS_KEY is not set: anyone who can reach the API can use it")
            app.state.speech = speech_service or (
                DefaultSpeechService(settings) if settings.speech_enabled else None
            )
            # Background jobs, so startup is not delayed: summarize lessons left open last
            # time, and load the speech models.
            background = [
                asyncio.create_task(
                    _end_stale_lessons(app, timedelta(hours=settings.stale_lesson_hours))
                )
            ]
            if app.state.speech is not None:
                background.append(asyncio.create_task(_warm_up_speech(app.state.speech)))
            yield
            for task in background:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if app.state.speech is not None:
                await app.state.speech.close()

    app = FastAPI(title="Language Tutor API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Health stays public for uptime checks; everything else needs the access key.
    app.include_router(health.router, prefix="/api")
    for router in (auth.router, profiles.router, lessons.router, speech.router):
        app.include_router(router, prefix="/api", dependencies=[Depends(require_access_key)])
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


async def _warm_up_speech(speech_service: SpeechService) -> None:
    try:
        await speech_service.warm_up()
    except Exception:
        logger.exception("Loading speech models failed; speech requests will retry")
