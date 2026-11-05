/**
 * Money on the web client. [TC-7] [D-20]
 *
 * **Money is never a JavaScript number.** A `number` is an IEEE double,
 * and the project forbids floating point for money in every language, in
 * storage, in transit and in memory. The server sends every amount as a
 * JSON string in canonical form (`"1200.00"`); this module keeps it a
 * string from the wire to the screen.
 *
 * **The class does no arithmetic, on purpose.** The client never computes
 * a balance, a remainder or a total [TC-9] [D-31] — the server sends every
 * figure the screen shows. So there is no `add`, no `subtract` and no
 * comparison beyond "is this zero". A screen that wants a sum has found a
 * value the server should have sent.
 *
 * Mirrors `core/model/Money.kt` and `core/format/Numerals.kt`.
 */

/** Exactly what the server emits: no sign, no separator, two places. */
const WIRE = /^[0-9]+\.[0-9]{2}$/

/** What a person may type: digits, optional lakh/thousand commas, ≤2 places. */
const TYPED = /^[0-9]+(,[0-9]+)*(\.[0-9]{1,2})?$/

const TAKA = '৳'
const BANGLA_ZERO = '০'.charCodeAt(0)

export class MoneyFormatError extends Error {
  override name = 'MoneyFormatError'
}

export class Money {
  /** The canonical wire string, e.g. `"1200.00"`. */
  readonly wire: string

  private constructor(wire: string) {
    this.wire = wire
  }

  /**
   * Decode a server value. **Fails loudly on anything but a string in
   * canonical form** — above all on a JSON number, because a lenient
   * decoder that quietly accepts `1200` is exactly the failure mode the
   * Android serializer test exists to catch.
   *
   * @param raw The decoded JSON value
   * @throws MoneyFormatError When `raw` is not a canonical money string
   */
  static fromWire(raw: unknown): Money {
    if (typeof raw !== 'string') {
      throw new MoneyFormatError(`Money must arrive as a JSON string, got ${typeof raw}`)
    }
    if (!WIRE.test(raw)) {
      throw new MoneyFormatError(`'${raw}' is not canonical money (digits, '.', two places)`)
    }
    return new Money(raw)
  }

  /** Like {@link fromWire} for a field the server may leave null. */
  static fromWireOrNull(raw: unknown): Money | null {
    return raw === null || raw === undefined ? null : Money.fromWire(raw)
  }

  /**
   * Read what a person typed: Bangla or Latin digits, an optional ৳,
   * optional grouping commas, up to two decimal places. Returns null for
   * anything else, rather than guessing.
   *
   * @param typed The raw field text
   */
  static fromTyped(typed: string): Money | null {
    const latin = toLatinDigits(typed.trim().replace(TAKA, '').trim())
    if (!TYPED.test(latin)) return null
    const [whole = '0', fraction = ''] = latin.replace(/,/g, '').split('.')
    const trimmed = whole.replace(/^0+(?=\d)/, '')
    return new Money(`${trimmed}.${fraction.padEnd(2, '0')}`)
  }

  /**
   * Order two amounts: -1, 0 or 1. Exact, on the decimal strings.
   *
   * **For shaping a form, never for deciding anything.** Its one use is
   * the partial-approval sheet, which asks "carry forward or waive?" only
   * when the amount the teacher *typed* is below what was reported — a
   * question the server cannot answer before it is asked. The server
   * re-checks the same thing and refuses a disposition that does not
   * apply, so a wrong answer here costs a message, not money.
   */
  compare(other: Money): -1 | 0 | 1 {
    const [aw = '0', af = '00'] = this.wire.split('.')
    const [bw = '0', bf = '00'] = other.wire.split('.')
    const a = aw.replace(/^0+(?=\d)/, '') + af
    const b = bw.replace(/^0+(?=\d)/, '') + bf
    if (a.length !== b.length) return a.length < b.length ? -1 : 1
    return a === b ? 0 : a < b ? -1 : 1
  }

  /** True when the amount is exactly zero. */
  isZero(): boolean {
    return /^0+\.00$/.test(this.wire)
  }

  /**
   * Render for a person: `৳1,20,000`, whole taka, lakh grouping, Western
   * digits in both languages (the design's numeral rule).
   *
   * Rounds half-up to whole taka **on the decimal string**, never through
   * a float, exactly as `Numerals.money` does.
   */
  format(): string {
    const [whole = '0', fraction = '00'] = this.wire.split('.')
    const rounded = (fraction[0] ?? '0') >= '5' ? incrementDigits(whole) : whole
    return TAKA + groupByLakh(rounded.replace(/^0+(?=\d)/, ''))
  }

  /** Render with paisa when there are any: `৳1,200.50`, else `৳1,200`. */
  formatExact(): string {
    const [whole = '0', fraction = '00'] = this.wire.split('.')
    const grouped = TAKA + groupByLakh(whole.replace(/^0+(?=\d)/, ''))
    return fraction === '00' ? grouped : `${grouped}.${fraction}`
  }

  toJSON(): string {
    return this.wire
  }

  /**
   * **Refuse to become a number.** Without this, `+money`, `money * 2` or
   * `money > other` would coerce through `toString()` to a JS double —
   * the float this module exists to keep out. String contexts (template
   * literals, `String(money)`) still get the wire form.
   */
  [Symbol.toPrimitive](hint: 'number' | 'string' | 'default'): string {
    if (hint === 'number') throw new TypeError('Money is not a number. Use format() or wire.')
    return this.wire
  }

  toString(): string {
    return this.wire
  }
}

/** `1234567` → `12,34,567`. */
export function groupByLakh(digits: string): string {
  if (digits.length <= 3) return digits
  const last3 = digits.slice(-3)
  let rest = digits.slice(0, -3)
  const groups: string[] = []
  while (rest.length > 2) {
    groups.unshift(rest.slice(-2))
    rest = rest.slice(0, -2)
  }
  if (rest) groups.unshift(rest)
  return [...groups, last3].join(',')
}

/** Add one to a string of decimal digits, with carry. */
function incrementDigits(digits: string): string {
  const out = digits.split('')
  for (let i = out.length - 1; i >= 0; i--) {
    if (out[i] === '9') {
      out[i] = '0'
    } else {
      out[i] = String.fromCharCode((out[i] ?? '0').charCodeAt(0) + 1)
      return out.join('')
    }
  }
  return '1' + out.join('')
}

/** Map Bangla digits ০–৯ to 0–9, leaving every other character alone. */
export function toLatinDigits(text: string): string {
  return text.replace(/[০-৯]/g, (d) => String(d.charCodeAt(0) - BANGLA_ZERO))
}
