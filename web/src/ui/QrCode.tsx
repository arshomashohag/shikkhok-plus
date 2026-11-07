/**
 * A QR code for the authenticator setup, drawn as an SVG.
 *
 * The encoder is `qrcode-generator` (MIT, no dependencies). Both apps use
 * it: the admin app's log-in and the main app's two-step verification
 * setup, which loads it with that screen's lazy chunk. It is drawn
 * **black on white with a four-module quiet zone in every theme**: a phone
 * camera reads dark modules on a light ground, and a dark-mode inversion
 * or a missing margin is the usual reason a code on a screen will not
 * scan.
 */
import qrcode from 'qrcode-generator'
import { useMemo } from 'react'

/** The margin the QR specification asks for, in modules. */
export const QUIET_ZONE = 4

/** The modules of `text`, encoded at error-correction level M. */
export function qrModules(text: string): boolean[][] {
  const qr = qrcode(0, 'M')
  qr.addData(text, 'Byte')
  qr.make()
  const n = qr.getModuleCount()
  return Array.from({ length: n }, (_, row) =>
    Array.from({ length: n }, (_, col) => qr.isDark(row, col)),
  )
}

/** One SVG path covering every dark module, offset by the quiet zone. */
export function qrPath(modules: boolean[][]): string {
  const parts: string[] = []
  modules.forEach((cells, row) => {
    cells.forEach((dark, col) => {
      if (dark) parts.push(`M${col + QUIET_ZONE} ${row + QUIET_ZONE}h1v1h-1z`)
    })
  })
  return parts.join('')
}

/**
 * @param moduleSize Pixels per module: a whole number, so every module is
 *   drawn the same size and the edges stay sharp
 */
export function QrCode({
  text,
  label,
  moduleSize = 4,
}: {
  text: string
  label: string
  moduleSize?: number
}) {
  const { path, extent } = useMemo(() => {
    const modules = qrModules(text)
    return { path: qrPath(modules), extent: modules.length + QUIET_ZONE * 2 }
  }, [text])
  return (
    <svg
      className="qr-code"
      role="img"
      aria-label={label}
      width={extent * moduleSize}
      height={extent * moduleSize}
      viewBox={`0 0 ${extent} ${extent}`}
      shapeRendering="crispEdges"
      data-modules={extent - QUIET_ZONE * 2}
    >
      <rect width={extent} height={extent} fill="#FFFFFF" />
      <path d={path} fill="#000000" />
    </svg>
  )
}
