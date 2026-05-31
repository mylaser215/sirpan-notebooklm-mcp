---
bundle_name: Sample1_Bundle
bundled_files:
  - mini_util_a.md
  - mini_util_b.py
  - mini_util_c.json
generated_at: 2026-05-31T19:38
generator: scripts/generate_bundle_md.py
bundle_sha256: 17743f13ee65a6c74b5869866ecab09743005e64a200a416cc70df594d223bd5
---

> [!warning] Facade — 읽기 전용 자동 산출물
> 본 소스는 다음 3개 파일의 통합본입니다. **수정은 개별 원본 파일을 이용하십시오.**
> - `mini_util_a.md`
> - `mini_util_b.py`
> - `mini_util_c.json`
> 자동 동기화 도구: `scripts/generate_bundle_md.py`

### 파일: mini_util_a.md

# mini util A — 텍스트 노트

본 파일은 generate_bundle_md.py 회귀 가드용 fixture입니다.

## 사용 예

`mini_util_a`는 라우팅 결정의 일관성을 검증하기 위한 *읽기 전용* 샘플입니다.

- 항목 1
- 항목 2

### 파일: mini_util_b.py

```python
"""mini util B — generate_bundle_md.py fixture (Python)."""


def add(x: int, y: int) -> int:
    return x + y


def mul(x: int, y: int) -> int:
    return x * y
```

### 파일: mini_util_c.json

```json
{
  "name": "mini_util_c",
  "kind": "fixture",
  "purpose": "generate_bundle_md regression"
}
```
