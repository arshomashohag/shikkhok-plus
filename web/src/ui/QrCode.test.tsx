import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { QrCode, qrModules, qrPath, QUIET_ZONE } from './QrCode'

const URI =
  'otpauth://totp/ShikkhokPlus%20Admin%3A%2B8801711234567?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=ShikkhokPlus%20Admin&algorithm=SHA1&digits=6&period=30'

/** A finder pattern: a 7×7 dark ring, a light ring, a 3×3 dark centre. */
function isFinder(m: boolean[][], top: number, left: number): boolean {
  for (let r = 0; r < 7; r++)
    for (let c = 0; c < 7; c++) {
      const ring = r === 0 || r === 6 || c === 0 || c === 6
      const centre = r >= 2 && r <= 4 && c >= 2 && c <= 4
      if (m[top + r]![left + c] !== (ring || centre)) return false
    }
  return true
}

describe('QR code', () => {
  it('encodes an otpauth URI as a valid symbol: square, finder patterns in three corners', () => {
    const m = qrModules(URI)
    const n = m.length
    expect((n - 17) % 4).toBe(0) // version v has 17 + 4v modules a side
    expect(n).toBeGreaterThanOrEqual(41)
    expect(m.every((row) => row.length === n)).toBe(true)
    expect(isFinder(m, 0, 0)).toBe(true)
    expect(isFinder(m, 0, n - 7)).toBe(true)
    expect(isFinder(m, n - 7, 0)).toBe(true)
    expect(isFinder(m, n - 7, n - 7)).toBe(false)
  })

  it('draws black on white with a four-module quiet zone, whatever the theme', () => {
    const { container } = render(<QrCode text={URI} label="QR" />)
    const svg = container.querySelector('svg')!
    const n = qrModules(URI).length
    expect(svg.getAttribute('viewBox')).toBe(`0 0 ${n + 2 * QUIET_ZONE} ${n + 2 * QUIET_ZONE}`)
    expect(svg.querySelector('rect')!.getAttribute('fill')).toBe('#FFFFFF')
    expect(svg.querySelector('path')!.getAttribute('fill')).toBe('#000000')
    // The first dark module (the top-left finder's corner) sits inside the margin.
    expect(qrPath(qrModules(URI)).startsWith(`M${QUIET_ZONE} ${QUIET_ZONE}`)).toBe(true)
  })
})
