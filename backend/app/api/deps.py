import asyncio
from collections import defaultdict
from typing import Annotated

from fastapi import Depends, Request
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.agent.summarizer import Summarizer
from app.config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> BaseStore:
    return request.app.state.persistence.store


def get_tutor(request: Request) -> CompiledStateGraph:
    return request.app.state.tutor


def get_summarizer(request: Request) -> Summarizer:
    return request.app.state.summarizer


def get_lesson_locks(request: Request) -> defaultdict[str, asyncio.Lock]:
    """One lock per lesson, so a lesson never runs two agent turns at once."""
    return request.app.state.lesson_locks


SettingsDep = Annotated[Settings, Depends(get_settings)]
StoreDep = Annotated[BaseStore, Depends(get_store)]
TutorDep = Annotated[CompiledStateGraph, Depends(get_tutor)]
SummarizerDep = Annotated[Summarizer, Depends(get_summarizer)]
LessonLocksDep = Annotated[defaultdict[str, asyncio.Lock], Depends(get_lesson_locks)]
