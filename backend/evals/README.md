# Tutor evals

These evals measure how well the tutor behaves on the real model. Run them before changing the tutor's prompt, tools, model or effort, and compare the result with a saved baseline.

They call the paid Anthropic API, so they never run in CI. `tests/test_evals.py` checks the harness itself with a fake model and does run in CI.

## What is measured

| Metric | How | What it covers |
|---|---|---|
| Reply format | code | At most 10 sentences and 2 questions, no markdown or emoji, no question in a closing message |
| Tool use | code | Mistakes recorded (and none for correct English), `original` is the learner's wording, one correction without "A / B" (in the tool call and in the reply's quoted wording; `mistake_age` may name both "I am 30" and "I'm 30" in the reply), the right tools called and wrong ones avoided, lesson clock |
| Judge | LLM | Concrete yes/no criteria per case: intent resolution and task adherence |
| Overall | all three | A case passes only if every metric passes |

Asking about two things at once is allowed, for example "What is your job, and why do you like it?".

The 37 cases are in `cases.py`, in five groups: `mistakes`, `no_mistakes`, `intent`, `adherence`, `clock`. `CASES.md` is a readable export. Only the reply to the last learner message is graded.

Each case runs through the app's real `LessonService`, LangGraph agent, prompt and tools, on a temporary data directory. Moderation is off, because it has its own tests.

The judge is Claude Haiku 5.5, the same model as the tutor, so it may share the tutor's blind spots. To try a stronger one, pass `--judge-model`. Scores from different judges are not comparable.

## Commands

Run from `backend/`.

```bash
uv run python -m evals.run --list
```

```bash
uv run python -m evals.run --export-cases
```

```bash
uv run python -m evals.run --cases mistake_age,clean_informal
```

```bash
uv run python -m evals.run --reps 2 --variant v1
```

Results go to `evals/runs/tutor/<variant>/` (gitignored): `results.jsonl`, `errors.jsonl` and one transcript per case in `traces/`. A rerun of the same variant skips finished cases, so delete the variant's folder to start over. API errors and timeouts go to `errors.jsonl` and never count as failures of the tutor.
