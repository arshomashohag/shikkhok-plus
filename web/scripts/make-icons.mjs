// Render the PWA's PNG icons from public/icons/mark.svg.
//
// Run by hand when the mark changes; the PNGs are committed. Uses the
// Playwright Chromium available in development, so CI never needs it.
//
//  * icon-192 / icon-512: "any" purpose, the mark cropped to its safe zone
//    on a rounded tile, which is how desktop launchers show it.
//  * icon-maskable-512: the full 108-unit canvas, so the platform's mask
//    crops into the background exactly as Android's adaptive icon does.
//  * apple-touch-icon: 180px, square; iOS rounds it.
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')
const icons = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons')
const mark = readFileSync(join(icons, 'mark.svg'), 'utf8')
const favicon = readFileSync(join(icons, 'favicon.svg'), 'utf8')

const jobs = [
  { file: 'icon-192.png', size: 192, svg: favicon, transparent: true },
  { file: 'icon-512.png', size: 512, svg: favicon, transparent: true },
  { file: 'icon-maskable-512.png', size: 512, svg: mark },
  {
    file: 'apple-touch-icon.png',
    size: 180,
    svg: mark.replace('viewBox="0 0 108 108"', 'viewBox="12 12 84 84"'),
  },
]

const browser = await chromium.launch()
for (const job of jobs) {
  const page = await browser.newPage({ viewport: { width: job.size, height: job.size } })
  const sized = job.svg.replace('<svg ', `<svg width="${job.size}" height="${job.size}" `)
  await page.setContent(
    `<html><body style="margin:0;background:transparent">${sized}</body></html>`,
  )
  await page.screenshot({ path: join(icons, job.file), omitBackground: !!job.transparent })
  await page.close()
}
await browser.close()
console.log('icons written')
