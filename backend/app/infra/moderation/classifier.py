"""The moderation classifier: a local Hugging Face model (`unitary/unbiased-toxic-roberta`,
the "unbiased" Detoxify model). It runs on the CPU in about 50 ms, so it adds almost no
delay, costs nothing and the message never leaves the server for this check. It is
trained on English text.
"""

import asyncio
import logging
import threading

from app.domain.moderation.policy import ALLOWED, ModerationVerdict, decide, strip_quoted

logger = logging.getLogger(__name__)

# The classifier reads at most 512 tokens; longer messages are scored in chunks.
_CHUNK_CHARS = 1000


class LocalModerator:
    """The Hugging Face classifier in this process, loaded on first use (on the CPU)."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._pipeline = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._pipeline is None:
                # Imported here, so tests and the app's startup do not pay for it.
                from transformers import pipeline

                self._pipeline = pipeline(
                    "text-classification",
                    model=self._model_name,
                    top_k=None,  # every label, not just the top one
                    function_to_apply="sigmoid",  # labels are independent (multi-label)
                    device="cpu",
                )
            return self._pipeline

    def _scores(self, text: str) -> dict[str, float]:
        """Highest score per label over the message's chunks."""
        chunks = [text[i : i + _CHUNK_CHARS] for i in range(0, len(text), _CHUNK_CHARS)]
        scores: dict[str, float] = {}
        for result in self._load()(chunks, truncation=True):
            for item in result:
                scores[item["label"]] = max(scores.get(item["label"], 0.0), item["score"])
        return scores

    async def check(self, text: str) -> ModerationVerdict:
        used = strip_quoted(text)
        if not used.strip():
            return ALLOWED
        try:
            scores = await asyncio.to_thread(self._scores, used)
        except Exception:
            # A broken check must not stop the lesson: let the message through, loudly.
            logger.exception("Moderation check failed; the message was let through")
            return ALLOWED
        return decide(used, scores)

    async def warm_up(self) -> None:
        await asyncio.to_thread(self._load)
