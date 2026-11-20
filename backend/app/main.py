import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models import BaseChatModel

from app.agent.graph import build_model, build_tutor_agent
from app.agent.summarizer import Summarizer, build_summarizer
from app.agent.wrapup import end_stale_lessons
from app.api import auth, health, lessons, profiles, speech
from app.api.auth import AuthLimiters
from app.api.security import RateLimiter
from app.auth.store import UserStore
from app.config import Settings, get_settings
from app.safety.moderation import LocalModerator, Moderator
from app.speech.service import DefaultSpeechService, SpeechService
from app.storage.persistence import open_persistence

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    model: BaseChatModel | None = None,
    summarizer: Summarizer | None = None,
    speech_service: SpeechService | None = None,
    moderator: Moderator | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own settings (temp data dir) and fakes for the models."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with (
            open_persistence(settings) as persistence,
            UserStore.open(
                settings.users_db_path,
                session_idle=timedelta(days=settings.session_idle_days),
                session_max=timedelta(days=settings.session_max_days),
            ) as users,
            httpx.AsyncClient() as http,
        ):
            await users.purge()
            app.state.users = users
            app.state.http = http
            app.state.auth_limiters = AuthLimiters.from_settings(settings)
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
            app.state.speech = speech_service or (
                DefaultSpeechService(settings) if settings.speech_enabled else None
            )
            app.state.moderator = moderator or (
                LocalModerator(settings.moderation_model) if settings.moderation_enabled else None
            )
            # Background jobs, so startup is not delayed: summarize lessons left open last
            # time, and load the speech and moderation models.
            background = [
                asyncio.create_task(
                    _end_stale_lessons(app, timedelta(hours=settings.stale_lesson_hours))
                )
            ]
            if app.state.speech is not None:
                background.append(asyncio.create_task(_warm_up_speech(app.state.speech)))
            if app.state.moderator is not None:
                background.append(asyncio.create_task(_warm_up_moderator(app.state.moderator)))
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
    # Health, signup and login are public; every other endpoint requires a session
    # (each one depends on the signed-in user).
    for router in (health.router, auth.router, profiles.router, lessons.router, speech.router):
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


async def _warm_up_speech(speech_service: SpeechService) -> None:
    try:
        await speech_service.warm_up()
    except Exception:
        logger.exception("Loading speech models failed; speech requests will retry")


async def _warm_up_moderator(moderator: Moderator) -> None:
    try:
        await moderator.warm_up()
    except Exception:
        logger.exception("Loading the moderation model failed; checks will retry")
