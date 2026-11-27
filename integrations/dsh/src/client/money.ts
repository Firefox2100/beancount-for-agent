/** A decimal written with commas between thousands (`-1,234,567.80`). Works on the text, so nothing passes through a float. */
export function grouped(value: string | number): string {
  const match = /^([+-]?)(\d+)(\.\d+)?$/.exec(String(value))
  return match === null ? String(value) : `${match[1]}${match[2]!.replace(/\B(?=(\d{3})+$)/g, ',')}${match[3] ?? ''}`
}

/** Per-currency amounts on one line: `1,200.00 GBP · 30 USD`. */
export function heldLine(values: Record<string, string | number>, separator = ' · '): string {
  return Object.entries(values).map(([currency, number]) => `${grouped(number)} ${currency}`).join(separator)
}

/** A number held as a float (a sum across accounts) at two places, grouped. */
export function fixed(value: number): string {
  return grouped(value.toFixed(2))
}
