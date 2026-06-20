/**
 * Strip Markdown code fences (```lang ... ```) that models often wrap code in,
 * returning just the inner source. No-op if there are no fences.
 */
export function stripCodeFences(text: string): string {
  const trimmed = text.trim();
  const fenced = trimmed.match(/^```[a-zA-Z0-9_-]*\s*\n([\s\S]*?)\n```$/);
  if (fenced && fenced[1] !== undefined) return fenced[1].trim();
  // Defensive fallback: drop a leading ```lang line and a trailing ``` if present.
  return trimmed
    .replace(/^```[a-zA-Z0-9_-]*\s*\n?/, "")
    .replace(/\n?```$/, "")
    .trim();
}

/** Remove duplicate strings, preserving order. */
export function dedupe(items: string[]): string[] {
  return [...new Set(items)];
}
