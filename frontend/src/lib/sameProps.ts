/**
 * Props comparison for React.memo on display panels: the server sends fresh
 * objects every poll even when nothing changed, so compare by value.
 * Dates compare by time; functions and primitives by identity.
 */
export function sameProps(a: object, b: object): boolean {
  const ka = Object.keys(a);
  if (ka.length !== Object.keys(b).length) return false;
  return ka.every((k) => sameValue((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]));
}

function sameValue(x: unknown, y: unknown): boolean {
  if (Object.is(x, y)) return true;
  if (x instanceof Date && y instanceof Date) return x.getTime() === y.getTime();
  if (typeof x === "object" && typeof y === "object" && x !== null && y !== null) {
    return JSON.stringify(x) === JSON.stringify(y);
  }
  return false;
}
