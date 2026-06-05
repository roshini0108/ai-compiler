import type { JsonValue } from "../types";

export function prettyJson(value: unknown): string {
  if (value === undefined) {
    return "";
  }

  return JSON.stringify(value, null, 2);
}

export function countItems(value: JsonValue | undefined, key: string): number | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }

  const candidate = value[key];
  return Array.isArray(candidate) ? candidate.length : undefined;
}

export function elapsed(start?: number, end?: number): string {
  if (!start) {
    return "";
  }

  const stop = end ?? Date.now();
  return `${Math.max(0.1, (stop - start) / 1000).toFixed(1)}s`;
}

export function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
