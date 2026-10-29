from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from app.agent.prompts import build_system_prompt
from app.agent.state import TutorState
from app.agent.tools import TUTOR_TOOLS
from app.config import Settings


@dynamic_prompt
def tutor_prompt(request: ModelRequest) -> str:
    return build_system_prompt(request.state)


def build_model(settings: Settings) -> BaseChatModel:
    return init_chat_model(
        settings.llm_model,
        api_key=settings.anthropic_api_key,
        max_tokens=4096,
        output_config={"effort": settings.tutor_effort},
        # Thinking blocks are bound to the exact system prompt, tools and history that
        # produced them. If those change (e.g. we edit a tool description while a lesson
        # is in progress), drop the stale thinking instead of failing the request.
        thinking={"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
        betas=["thinking-binding-controls-2026-08-01"],
    )


def build_tutor_agent(model: BaseChatModel, checkpointer: BaseCheckpointSaver, store: BaseStore):
    """The tutor: a tool-calling agent whose state is one lesson (thread_id = lesson id)."""
    return create_agent(
        model,
        tools=TUTOR_TOOLS,
        middleware=[tutor_prompt],
        state_schema=TutorState,
        checkpointer=checkpointer,
        store=store,
        name="tutor",
    )
