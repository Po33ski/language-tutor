"""Run the tutor evals. Every run except --list and --export-cases calls the paid API.

uv run python -m evals.run --list
uv run python -m evals.run --export-cases
uv run python -m evals.run --cases mistake_age,clean_informal
uv run python -m evals.run --reps 2 --variant v1
"""

import argparse
import asyncio
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from app.config import Settings
from app.infra.agent.graph import build_model
from evals.cases import CASES
from evals.checks import clock_failures, format_failures, tool_failures
from evals.harness import run_case
from evals.judge import DEFAULT_JUDGE_MODEL, build_judge, judge_case
from evals.schema import Case, CaseRun

EVALS_DIR = Path(__file__).parent
RUNS_DIR = EVALS_DIR / "runs" / "tutor"
METRICS = [
    {"id": "overall", "label": "Overall", "kind": "binary"},
    {"id": "format", "label": "Reply format", "kind": "binary"},
    {"id": "tools", "label": "Tool use", "kind": "binary"},
    {"id": "judge", "label": "Judge", "kind": "binary"},
]


def wilson_interval(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    rate = passed / total
    denominator = 1 + z**2 / total
    center = (rate + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / total + z**2 / (4 * total**2)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _model_name(model_id: str) -> str:
    return model_id.split(":", 1)[-1]


def _check_served(requested: str, served: str | None) -> None:
    if not served or not served.startswith(_model_name(requested)):
        raise RuntimeError(f"served model {served!r}, requested {requested!r}")


def grade_programmatic(case: Case, run: CaseRun) -> tuple[bool, bool, list[str]]:
    """Returns (format passed, tools passed, failure notes)."""
    format_notes = format_failures(run.graded.reply, closing=case.expect_time_up)
    tool_notes = tool_failures(case, run) + clock_failures(case, run)
    return not format_notes, not tool_notes, format_notes + tool_notes


def trace(case: Case, run: CaseRun) -> list[dict]:
    turns: list[dict] = [{"role": "system", "content": run.system_prompt}]
    for turn in run.turns:
        turns.append({"role": "user", "content": turn.learner})
        for call in turn.tool_calls:
            content = json.dumps(call.args, indent=2, ensure_ascii=False)
            turns.append({"role": "tool_call", "name": call.name, "content": content})
        turns.append({"role": "assistant", "content": turn.reply})
    return turns


async def evaluate(case, rep, model, judge, args) -> dict:
    started = time.monotonic()
    run = await run_case(case, model)
    latency = time.monotonic() - started
    _check_served(args.model, run.model)

    truncated = run.stop_reason == "max_tokens"
    format_ok, tools_ok, notes = grade_programmatic(case, run)
    judge_ok, unmet, judge_usage, judge_served = await judge_case(judge, case, run)
    if judge_served is not None:
        _check_served(args.judge_model, judge_served)
    row = {
        "prompt_id": case.id,
        "rep": rep,
        "prompt": "\n".join(case.turns),
        "tags": [case.tag, case.level],
        "status": "truncated" if truncated else "ok",
        "stop_reason": run.stop_reason,
        "grade": {
            "overall": int(format_ok and tools_ok and judge_ok),
            "format": int(format_ok),
            "tools": int(tools_ok),
            "judge": int(judge_ok),
        },
        "explanation": {"overall": "; ".join(notes + unmet) or "all checks passed"},
        "model": run.model,
        "usage": run.usage,
        "judge_model": judge_served,
        "judge_usage": judge_usage,
        "latency_s": round(latency, 2),
        "tool_calls": len(run.graded.tool_calls),
    }
    return {"row": row, "trace": trace(case, run)}


def _completed(results: Path) -> set[tuple[str, int]]:
    if not results.exists():
        return set()
    rows = [json.loads(line) for line in results.read_text().splitlines() if line.strip()]
    return {(row["prompt_id"], row["rep"]) for row in rows}


def _summary(results: Path, errors: int) -> None:
    rows = [json.loads(line) for line in results.read_text().splitlines() if line.strip()]
    scored = [row for row in rows if row["status"] == "ok"]
    passed = sum(row["grade"]["overall"] for row in scored)
    low, high = wilson_interval(passed, len(scored))
    if scored:
        print(
            f"\nOverall: {passed}/{len(scored)} = {passed / len(scored):.0%} "
            f"(95% CI {low:.0%}-{high:.0%}); truncated: {len(rows) - len(scored)}, "
            f"errors this run: {errors}"
        )
    for metric in ("format", "tools", "judge"):
        hits = sum(row["grade"][metric] for row in scored)
        print(f"  {metric:8} {hits}/{len(scored)}")
    by_tag: dict[str, list[int]] = defaultdict(list)
    for row in scored:
        by_tag[row["tags"][0]].append(row["grade"]["overall"])
    for tag, grades in by_tag.items():
        print(f"  [{tag}] {sum(grades)}/{len(grades)}")
    tokens = defaultdict(int)
    for row in rows:
        for source in (row["usage"], row["judge_usage"]):
            tokens["input"] += source.get("input_tokens", 0)
            tokens["output"] += source.get("output_tokens", 0)
    print(f"  tokens: {tokens['input']} input, {tokens['output']} output")


async def run_all(cases: list[Case], args) -> None:
    settings = Settings(llm_model=args.model)
    model = build_model(settings)
    judge = build_judge(args.judge_model, settings.anthropic_api_key)

    variant_dir = RUNS_DIR / args.variant
    (variant_dir / "traces").mkdir(parents=True, exist_ok=True)
    state_path = RUNS_DIR / "_state.json"
    if not state_path.exists():
        state_path.write_text(json.dumps({"metrics": METRICS}, indent=2))
    results = variant_dir / "results.jsonl"
    errors_path = variant_dir / "errors.jsonl"
    done = _completed(results)
    work = [(case, rep) for case in cases for rep in range(args.reps) if (case.id, rep) not in done]
    semaphore = asyncio.Semaphore(args.concurrency)
    failed = 0

    async def one(case: Case, rep: int) -> None:
        nonlocal failed
        async with semaphore:
            try:
                output = await asyncio.wait_for(
                    evaluate(case, rep, model, judge, args), args.timeout
                )
            except Exception as error:
                failed += 1
                kind = "timeout" if isinstance(error, TimeoutError) else type(error).__name__
                with errors_path.open("a") as handle:
                    entry = {"prompt_id": case.id, "rep": rep, "class": kind, "error": str(error)}
                    handle.write(json.dumps(entry) + "\n")
                print(f"ERROR {case.id}#{rep}: {kind}", flush=True)
                return
        row = output["row"]
        trace_path = variant_dir / "traces" / f"{case.id}_rep{rep}.json"
        trace_path.write_text(json.dumps(output["trace"], indent=1, ensure_ascii=False))
        with results.open("a") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        mark = "PASS" if row["grade"]["overall"] else "FAIL"
        print(f"{mark}  {case.id}#{rep}  {row['explanation']['overall'][:150]}", flush=True)

    await asyncio.gather(*(one(case, rep) for case, rep in work))
    if results.exists():
        _summary(results, failed)
    print(f"\nResults: {variant_dir}")


def export_cases(path: Path) -> None:
    lines = ["# Tutor eval cases", "", f"{len(CASES)} cases. Generated by `--export-cases`.", ""]
    lines += ["| Id | Group | Level | Minute | Mistakes | Must call | Must not call |"]
    lines += ["|---|---|---|---|---|---|---|"]
    for case in CASES:
        most = "any" if case.mistakes_max is None else case.mistakes_max
        lines.append(
            f"| `{case.id}` | {case.tag} | {case.level} | {case.elapsed_minutes:g}/{case.minutes} "
            f"| {case.mistakes_min}–{most} | {', '.join(case.required_tools) or '–'} "
            f"| {', '.join(case.forbidden_tools) or '–'} |"
        )
    lines.append("")
    for case in CASES:
        lines += [f"## `{case.id}`", "", "Learner:", ""]
        lines += [f"> {text}" for text in case.turns]
        lines += ["", "The judge checks:", ""]
        lines += [f"- {criterion}" for criterion in case.criteria]
        if case.corrected_any:
            lines += ["", "A correction must contain:", ""]
            lines += [f"- {' or '.join(f'`{o}`' for o in group)}" for group in case.corrected_any]
        lines.append("")
    path.write_text("\n".join(lines))
    print(f"Wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list the cases (free)")
    parser.add_argument("--export-cases", action="store_true", help="write CASES.md (free)")
    parser.add_argument("--cases", help="comma-separated case ids")
    parser.add_argument("--tag", help="only this group of cases")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--variant", default="baseline", help="baseline or v1, v2, ...")
    parser.add_argument("--model", default=Settings().llm_model)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=180, help="seconds per case")
    args = parser.parse_args()

    cases = CASES
    if args.cases:
        wanted = set(args.cases.split(","))
        unknown = wanted - {case.id for case in CASES}
        if unknown:
            parser.error(f"unknown cases: {sorted(unknown)}")
        cases = [case for case in cases if case.id in wanted]
    if args.tag:
        cases = [case for case in cases if case.tag == args.tag]

    if args.list:
        for case in cases:
            print(f"{case.tag:12} {case.id}")
        print(f"{len(cases)} cases")
    elif args.export_cases:
        export_cases(EVALS_DIR / "CASES.md")
    else:
        asyncio.run(run_all(cases, args))


if __name__ == "__main__":
    main()
