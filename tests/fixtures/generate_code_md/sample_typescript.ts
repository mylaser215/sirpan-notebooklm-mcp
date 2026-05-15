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
