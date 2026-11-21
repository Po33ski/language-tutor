from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings
from app.domain.accounts.service import AccountService
from app.domain.lessons.service import LessonService
from app.domain.ports import AccountStore, LearnerMemory, SpeechService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_memory(request: Request) -> LearnerMemory:
    return request.app.state.memory


def get_lessons(request: Request) -> LessonService:
    return request.app.state.lessons


def get_accounts(request: Request) -> AccountService:
    return request.app.state.accounts


def get_users(request: Request) -> AccountStore:
    return request.app.state.users


def get_speech(request: Request) -> SpeechService:
    speech = request.app.state.speech
    if speech is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Speech is disabled")
    return speech


SettingsDep = Annotated[Settings, Depends(get_settings)]
MemoryDep = Annotated[LearnerMemory, Depends(get_memory)]
LessonsDep = Annotated[LessonService, Depends(get_lessons)]
AccountsDep = Annotated[AccountService, Depends(get_accounts)]
UsersDep = Annotated[AccountStore, Depends(get_users)]
SpeechDep = Annotated[SpeechService, Depends(get_speech)]
