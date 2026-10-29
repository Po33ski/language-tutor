import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models import BaseChatModel

from app.agent.graph import build_model, build_tutor_agent
from app.api import health, lessons, profiles
from app.config import Settings, get_settings
from app.storage.persistence import open_persistence


def create_app(settings: Settings | None = None, model: BaseChatModel | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings (temp data dir) and a fake model."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with open_persistence(settings) as persistence:
            app.state.settings = settings
            app.state.persistence = persistence
            app.state.tutor = build_tutor_agent(
                model or build_model(settings), persistence.checkpointer, persistence.store
            )
            app.state.lesson_locks = defaultdict(asyncio.Lock)
            yield

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
