import asyncio
from collections import defaultdict
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.agent.summarizer import Summarizer
from app.auth.store import UserStore
from app.config import Settings
from app.safety.moderation import Moderator
from app.speech.service import SpeechService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> BaseStore:
    return request.app.state.persistence.store


def get_tutor(request: Request) -> CompiledStateGraph:
    return request.app.state.tutor


def get_summarizer(request: Request) -> Summarizer:
    return request.app.state.summarizer


def get_speech(request: Request) -> SpeechService:
    speech = request.app.state.speech
    if speech is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Speech is disabled")
    return speech


def get_moderator(request: Request) -> Moderator | None:
    """The message classifier; None when moderation is off (`MODERATION_ENABLED=false`)."""
    return request.app.state.moderator


def get_lesson_locks(request: Request) -> defaultdict[str, asyncio.Lock]:
    """One lock per lesson, so a lesson never runs two agent turns at once."""
    return request.app.state.lesson_locks


def get_users(request: Request) -> UserStore:
    return request.app.state.users


def get_http(request: Request) -> httpx.AsyncClient:
    """Shared HTTP client for outgoing calls (the breached-password check)."""
    return request.app.state.http


SettingsDep = Annotated[Settings, Depends(get_settings)]
UsersDep = Annotated[UserStore, Depends(get_users)]
HttpDep = Annotated[httpx.AsyncClient, Depends(get_http)]
StoreDep = Annotated[BaseStore, Depends(get_store)]
TutorDep = Annotated[CompiledStateGraph, Depends(get_tutor)]
SummarizerDep = Annotated[Summarizer, Depends(get_summarizer)]
SpeechDep = Annotated[SpeechService, Depends(get_speech)]
ModeratorDep = Annotated[Moderator | None, Depends(get_moderator)]
LessonLocksDep = Annotated[defaultdict[str, asyncio.Lock], Depends(get_lesson_locks)]
