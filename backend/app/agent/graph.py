from typing import Any

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import ModelRequest, before_model, dynamic_prompt
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore

from app.agent.prompts import build_system_prompt
from app.agent.state import TutorState
from app.agent.tools import TUTOR_TOOLS
from app.config import Settings


@dynamic_prompt
def tutor_prompt(request: ModelRequest) -> str:
    return build_system_prompt(request.state)


@before_model(can_jump_to=["end"])
def end_turn_if_already_replied(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Skip the model call after tool results if the tutor already replied.

    The model sometimes writes its reply in the same message as its tool calls and then
    repeats it after the tool results, so the learner would see the reply twice.
    """
    messages = state["messages"]
    if not messages or not isinstance(messages[-1], ToolMessage):
        return None
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai is not None and last_ai.text.strip():
        return {"jump_to": "end"}
    return None


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
        middleware=[tutor_prompt, end_turn_if_already_replied],
        state_schema=TutorState,
        checkpointer=checkpointer,
        store=store,
        name="tutor",
    )
