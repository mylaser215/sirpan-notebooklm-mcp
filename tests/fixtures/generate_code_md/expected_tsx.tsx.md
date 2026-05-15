---
source_path: sample_tsx.tsx
generated_at: 2026-05-15T10:52
original_sha256: 167f6743e400f5c8b8145890eb0343c6f3a23c9681afecbe77b9dd7b4e9cc2a0
generator: scripts/generate_ts_md.py
---

## 아키텍처 요약

(TODO: 사용자 정성 작성 — 본 모듈의 책임 / 핵심 설계 패턴 / 의존 관계를 3-5단락으로 요약. 재생성 시 본 섹션은 *그대로 보존됨* — 멱등성)

## 코드 구조

### `ButtonProps` (line 4, *interface*)

```typescript
export interface ButtonProps {
```

### `Button` (line 9, *arrow*)

```typescript
export const Button = (props: ButtonProps) => {
```

## 원본 코드

```typescript
// Sample .tsx for generate_code_md regression fixture — verifies that
// .tsx files dispatch to the same regex parser as .ts.

export interface ButtonProps {
  label: string;
  onClick: () => void;
}

export const Button = (props: ButtonProps) => {
  return null;
};
```
