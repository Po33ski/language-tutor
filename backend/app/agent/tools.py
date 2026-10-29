from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.agent.state import Mistake, VocabularyItem
from app.storage import memory


@tool
def record_mistake(
    original: str, corrected: str, explanation: str, runtime: ToolRuntime
) -> Command:
    """Record a meaningful mistake the learner just made.

    Record each mistake once; do not record overlapping fragments of the same sentence
    as separate mistakes unless they are different errors.

    Args:
        original: The shortest fragment of the learner's exact wording that contains
            the mistake.
        corrected: The corrected, natural wording.
        explanation: One short sentence explaining the rule or why it is better.
    """
    mistake = Mistake(original=original, corrected=corrected, explanation=explanation)
    return Command(
        update={
            "mistakes": [mistake],
            "messages": [ToolMessage("Mistake recorded.", tool_call_id=runtime.tool_call_id)],
        }
    )


@tool
def add_vocabulary(word: str, meaning: str, example: str, runtime: ToolRuntime) -> Command:
    """Add a new word or phrase you are teaching to the learner's vocabulary list.

    Args:
        word: The word or phrase.
        meaning: A short, simple English definition.
        example: An example sentence related to the lesson topic.
    """
    item = VocabularyItem(word=word, meaning=meaning, example=example)
    return Command(
        update={
            "vocabulary": [item],
            "messages": [ToolMessage("Vocabulary added.", tool_call_id=runtime.tool_call_id)],
        }
    )


@tool
async def save_preference(key: str, value: str, runtime: ToolRuntime) -> str:
    """Save a lasting learning preference the learner stated, for all future lessons.

    Args:
        key: Short snake_case name, e.g. "correction_style" or "english_variant".
        value: The preference, e.g. "only correct major mistakes" or "British English".
    """
    user_id = runtime.state.get("user_id")
    if not user_id or runtime.store is None:
        return "Could not save the preference."
    await memory.save_preference(runtime.store, user_id, key, value)
    return "Preference saved."


TUTOR_TOOLS = [record_mistake, add_vocabulary, save_preference]
