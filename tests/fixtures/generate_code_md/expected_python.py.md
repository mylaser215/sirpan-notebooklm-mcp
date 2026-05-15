---
source_path: sample_python.py
generated_at: 2026-05-15T10:52
original_sha256: fd50d4293f99a0b08c5ffd11847e3be7a6b1153de1f095d6fdfa6a1296542887
generator: scripts/generate_py_md.py
---

## 아키텍처 요약

(TODO: 사용자 정성 작성 — 본 모듈의 책임 / 핵심 설계 패턴 / 의존 관계를 3-5단락으로 요약. 재생성 시 본 섹션은 *그대로 보존됨* — 멱등성)

## 함수별 역할

*모듈 docstring*: Sample Python module for generate_code_md regression fixture.

### `Greeter` (line 10)

```python
class Greeter
```

A simple greeter that demonstrates class extraction.

**Methods**:
- `__init__` (line 13) — Initialize with a name.
- `greet` (line 17) — Return a greeting string.

### `add` (line 22)

```python
def add(a: int, b: int) -> int
```

Return the sum of two integers.

### `fetch_async` (line 27)

```python
async def fetch_async(url: str) -> str
```

Pretend to fetch a URL asynchronously.

## 원본 코드

```python
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
```
