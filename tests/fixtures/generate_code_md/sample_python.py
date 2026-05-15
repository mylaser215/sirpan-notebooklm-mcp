"""Sample Python module for generate_code_md regression fixture.

Covers AST extraction cases: module docstring, class with methods,
top-level sync/async functions, and class-level docstring.
"""

from __future__ import annotations


class Greeter:
    """A simple greeter that demonstrates class extraction."""

    def __init__(self, name: str) -> None:
        """Initialize with a name."""
        self.name = name

    def greet(self) -> str:
        """Return a greeting string."""
        return f"Hello, {self.name}!"


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


async def fetch_async(url: str) -> str:
    """Pretend to fetch a URL asynchronously."""
    return f"fetched {url}"
