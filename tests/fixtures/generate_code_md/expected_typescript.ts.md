---
source_path: sample_typescript.ts
generated_at: 2026-05-15T10:52
original_sha256: 965ef97ad273daf2ed39a01ae0ba7a98769e860dd83915e4c3cbb646a111dcf6
generator: scripts/generate_ts_md.py
---

## 아키텍처 요약

(TODO: 사용자 정성 작성 — 본 모듈의 책임 / 핵심 설계 패턴 / 의존 관계를 3-5단락으로 요약. 재생성 시 본 섹션은 *그대로 보존됨* — 멱등성)

## 코드 구조

### `greet` (line 5, *function*)

```typescript
export function greet(name: string): string {
```

### `add` (line 9, *arrow*)

```typescript
export const add = (a: number, b: number): number => a + b;
```

### `Greeter` (line 11, *class*)

```typescript
export class Greeter {
```

### `Point` (line 19, *interface*)

```typescript
export interface Point {
```

### `Pair` (line 24, *type*)

```typescript
export type Pair<T> = [T, T];
```

### `Color` (line 26, *enum*)

```typescript
export enum Color {
```

## 원본 코드

```typescript
// Sample TypeScript module for generate_code_md regression fixture.
// Covers regex SYMBOL_PATTERNS 6 cases: function / arrow-const /
// class / interface / type / enum.

export function greet(name: string): string {
  return `Hello, ${name}!`;
}

export const add = (a: number, b: number): number => a + b;

export class Greeter {
  constructor(private readonly name: string) {}

  greet(): string {
    return `Hello, ${this.name}!`;
  }
}

export interface Point {
  x: number;
  y: number;
}

export type Pair<T> = [T, T];

export enum Color {
  Red = "red",
  Green = "green",
  Blue = "blue",
}
```
