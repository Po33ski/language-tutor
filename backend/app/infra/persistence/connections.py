from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore

from app.config import Settings


@dataclass
class Persistence:
    checkpointer: AsyncSqliteSaver  # short-term memory: lesson conversations
    store: AsyncSqliteStore  # long-term memory: profiles, lessons, summaries


@asynccontextmanager
async def open_persistence(settings: Settings) -> AsyncIterator[Persistence]:
    """Open the SQLite-backed checkpointer and store for the app's lifetime.

    They use separate files so their writes never contend for the same SQLite lock.
    """
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    async with (
        AsyncSqliteSaver.from_conn_string(str(settings.checkpoints_db_path)) as checkpointer,
        AsyncSqliteStore.from_conn_string(str(settings.memory_db_path)) as store,
    ):
        await checkpointer.setup()
        await store.setup()
        yield Persistence(checkpointer=checkpointer, store=store)
