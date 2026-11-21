"""The layers depend inward: api -> domain <- infra."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).parent.parent / "app"
# The domain may use Pydantic for its models; everything else stays outside it.
DOMAIN_FORBIDDEN = (
    "aiosqlite",
    "app.api",
    "app.config",
    "app.infra",
    "fastapi",
    "httpx",
    "langchain",
    "langchain_core",
    "langgraph",
    "pwdlib",
    "starlette",
    "transformers",
)


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _violations(layer: str, forbidden: tuple[str, ...]) -> list[str]:
    return [
        f"{path.relative_to(APP)} imports {name}"
        for path in (APP / layer).rglob("*.py")
        for name in _imports(path)
        if any(name == banned or name.startswith(f"{banned}.") for banned in forbidden)
    ]


@pytest.mark.parametrize(
    ("layer", "forbidden"),
    [
        ("domain", DOMAIN_FORBIDDEN),
        ("api", ("app.infra",)),
        ("infra", ("app.api",)),
    ],
)
def test_layer_boundaries(layer: str, forbidden: tuple[str, ...]) -> None:
    assert _violations(layer, forbidden) == []
