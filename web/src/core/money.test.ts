import { describe, expect, it } from 'vitest'
import { groupByLakh, Money, MoneyFormatError, toLatinDigits } from './money'

describe('Money.fromWire', () => {
  it('reads the canonical string the server sends', () => {
    expect(Money.fromWire('1200.00').wire).toBe('1200.00')
  })

  // The failure mode the Android MoneySerializerTest exists for: a lenient
  // decoder that quietly accepts a JSON number passes a happy-path test.
  it.each([1200, 1200.5, null, undefined, true, {}])('fails loudly on a non-string %p', (raw) => {
    expect(() => Money.fromWire(raw)).toThrow(MoneyFormatError)
  })

  it.each(['1200', '1200.5', '-5.00', '1,200.00', '১২০০.০০', ' 1200.00', '1e3'])(
    'fails loudly on a non-canonical string %p',
    (raw) => {
      expect(() => Money.fromWire(raw)).toThrow(MoneyFormatError)
    },
  )

  it('passes null through only via fromWireOrNull', () => {
    expect(Money.fromWireOrNull(null)).toBeNull()
    expect(() => Money.fromWireOrNull(5)).toThrow(MoneyFormatError)
  })
})

describe('Money.format', () => {
  it.each([
    ['0.00', '৳0'],
    ['400.00', '৳400'],
    ['1200.00', '৳1,200'],
    ['48600.00', '৳48,600'],
    ['120000.00', '৳1,20,000'],
    ['12345678.00', '৳1,23,45,678'],
  ])('%s → %s (lakh grouping)', (wire, shown) => {
    expect(Money.fromWire(wire).format()).toBe(shown)
  })

  // Rounding happens on the decimal string, half-up, never through a float.
  it.each([
    ['1200.49', '৳1,200'],
    ['1200.50', '৳1,201'],
    ['999.50', '৳1,000'],
    ['99999.99', '৳1,00,000'],
    ['0.50', '৳1'],
  ])('rounds %s half-up to %s', (wire, shown) => {
    expect(Money.fromWire(wire).format()).toBe(shown)
  })

  it('shows paisa only when there are any', () => {
    expect(Money.fromWire('1200.50').formatExact()).toBe('৳1,200.50')
    expect(Money.fromWire('1200.00').formatExact()).toBe('৳1,200')
  })
})

describe('Money.fromTyped', () => {
  it.each([
    ['1500', '1500.00'],
    ['1500.5', '1500.50'],
    ['1,500.50', '1500.50'],
    ['৳ 1,200', '1200.00'],
    ['১৫০০', '1500.00'],
    ['0800', '800.00'],
  ])('reads %p as %s', (typed, wire) => {
    expect(Money.fromTyped(typed)?.wire).toBe(wire)
  })

  it.each(['', 'abc', '1.234', '-5', '1 500', '12,'])('refuses %p', (typed) => {
    expect(Money.fromTyped(typed)).toBeNull()
  })
})

describe('Money.compare', () => {
  it.each([
    ['800.00', '1200.00', -1],
    ['1200.00', '1200.00', 0],
    ['1200.01', '1200.00', 1],
    ['10000.00', '9999.99', 1],
    ['0.99', '1.00', -1],
  ] as const)('%s vs %s → %i', (a, b, expected) => {
    expect(Money.fromWire(a).compare(Money.fromWire(b))).toBe(expected)
  })
})

it('exposes no arithmetic', () => {
  const m = Money.fromWire('1.00') as unknown as Record<string, unknown>
  for (const name of ['add', 'plus', 'subtract', 'minus', 'times', 'valueOf']) {
    expect(typeof m[name] === 'function' && name !== 'valueOf').toBe(false)
  }
  // No implicit numeric coercion: `+money` and `money * 2` throw.
  const money = Money.fromWire('1200.00') as unknown as number
  expect(() => +money).toThrow(TypeError)
  expect(() => money * 2).toThrow(TypeError)
  expect(() => money > 5).toThrow(TypeError)
  expect(`${Money.fromWire('1200.00') as unknown as string}`).toBe('1200.00')
})

it('groups by lakh and maps Bangla digits', () => {
  expect(groupByLakh('1234567')).toBe('12,34,567')
  expect(toLatinDigits('০১৭১১-২৩৪৫৬৭')).toBe('01711-234567')
})
