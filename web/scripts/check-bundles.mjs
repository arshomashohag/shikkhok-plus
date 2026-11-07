// Fail when the main app and the admin app leak into each other.
//
// The admin app is a separate build served from its own IP-restricted
// hostname. The main app is public, so it must carry no admin screen, no
// admin string and no admin API path: what is not shipped cannot be
// probed. And the admin build must carry none of the main app's PWA
// machinery or screens. Run after `npm run build` and `npm run build:admin`.
//
// Every "absent" check is paired with a "present" one on the other build,
// so a scan of an empty or wrong directory fails instead of passing.

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const web = join(dirname(fileURLToPath(import.meta.url)), '..')
const problems = []

/** A name only the QR encoder (`qrcode-generator`) carries through minification. */
const QR_ENCODER = 'getModuleCount'

/** Every shipped text file under `dir` (source maps excluded), as [path, text]. */
function shipped(dir) {
  const out = []
  const walk = (d) => {
    for (const name of readdirSync(d)) {
      const path = join(d, name)
      if (statSync(path).isDirectory()) walk(path)
      else if (/\.(js|mjs|css|html|webmanifest|json)$/.test(name))
        out.push([relative(dir, path), readFileSync(path, 'utf8')])
    }
  }
  walk(dir)
  return out
}

function scan(label, dir, { absent, present }) {
  if (!existsSync(dir)) {
    problems.push(`${label}: ${relative(web, dir)}/ does not exist; build it first`)
    return []
  }
  const files = shipped(dir)
  for (const [needle, why] of absent) {
    const found = (text) => (typeof needle === 'string' ? text.includes(needle) : needle.test(text))
    const hits = files.filter(([, text]) => found(text)).map(([f]) => f)
    if (hits.length) problems.push(`${label}: "${needle}" (${why}) found in ${hits.join(', ')}`)
  }
  for (const needle of present) {
    if (!files.some(([, text]) => text.includes(needle)))
      problems.push(`${label}: expected "${needle}" somewhere; is this the right build?`)
  }
  return files
}

// ------------------------------------------------------------- main app
// The main app has its own two-step verification since the authenticator
// sign-in step and settings were added, so `otpauth` and the QR encoder
// are expected in it now; what stays forbidden is everything admin-only.
const main = scan('dist', join(web, 'dist'), {
  absent: [
    ['/v1/admin', 'an admin API path'],
    ['web_admin_', 'an admin string key'],
    // Not "administrator": the server's `mfa.required_for_admin` message,
    // which the main app shows, names a ShikkhokPlus administrator's number.
    [/ShikkhokPlus admin(?!istrator)/, 'admin copy'],
    ['ShikkhokPlus%20Admin', "the admin authenticator's issuer"],
  ],
  present: ['/v1/me/today', '/v1/auth/verify', '/v1/auth/mfa', '/v1/me/mfa/setup', QR_ENCODER],
})
for (const [file] of main) {
  if (/admin/i.test(file)) problems.push(`dist: ${file} looks like an admin chunk`)
}
// The QR encoder is only for the settings screen: it must load with that
// lazy chunk, never in the entry chunk every visitor downloads.
const entry = main
  .find(([f]) => f === 'index.html')?.[1]
  ?.match(/src="[^"]*?(assets\/index-[^"]+\.js)"/)?.[1]
if (!entry) problems.push('dist: index.html names no entry chunk')
else if (main.find(([f]) => f === entry)?.[1]?.includes(QR_ENCODER))
  problems.push(
    `dist: the QR encoder is in the entry chunk ${entry}; load it with the settings screen`,
  )

// ------------------------------------------------------------ admin app
const adminDir = join(web, 'dist-admin')
const admin = scan('dist-admin', adminDir, {
  absent: [
    ['/v1/me/today', "a main-app screen's API path"],
    ['/v1/claims/queue', "a main-app screen's API path"],
    ['/v1/auth/refresh', 'app token renewal'],
    ['registerSW', 'the service worker'],
    ['workbox', 'the service worker'],
  ],
  present: ['/v1/admin/auth/mfa', '/v1/admin/overview', 'web_admin_', QR_ENCODER],
})
if (existsSync(adminDir)) {
  for (const name of ['sw.js', 'manifest.webmanifest', 'registerSW.js', 'admin.html']) {
    if (existsSync(join(adminDir, name))) problems.push(`dist-admin: ${name} must not be shipped`)
  }
  const index = admin.find(([f]) => f === 'index.html')?.[1]
  if (!index) problems.push('dist-admin: no index.html')
  else {
    const csp = index.match(/http-equiv="Content-Security-Policy" content="([^"]*)"/)?.[1] ?? ''
    if (!/(^|; )connect-src 'self'(;|$)/.test(csp))
      problems.push(`dist-admin: CSP connect-src must be exactly 'self', got: ${csp || '(none)'}`)
  }
}

if (problems.length) {
  console.error(problems.map((p) => `✗ ${p}`).join('\n'))
  process.exit(1)
}
console.log('✓ main and admin bundles are separate')
