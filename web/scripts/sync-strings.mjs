// Generate the web client's string bundles from the Android resources.
//
// **One source of truth for every user-facing string.** The Android
// bundles are complete in Bangla and English and are reviewed there; a
// second hand-kept copy here would drift within a unit. So the web reads
// the same keys, generated from `android/src/main/res/values{,-bn}`, and
// `check-generated.mjs` fails CI when this output is stale.
//
// The server's `message_key` → string mapping is generated the same way
// from MessageKeys.kt, so an error the server names renders identically
// on both clients.
//
// Usage: node scripts/sync-strings.mjs [--check]

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repo = join(here, '..', '..')
const res = join(repo, 'android', 'src', 'main', 'res')
const outDir = join(here, '..', 'src', 'i18n', 'generated')

/** Decode Android's string-resource escaping into plain text. */
function decode(raw) {
  let s = raw.trim()
  if (s.startsWith('"') && s.endsWith('"')) s = s.slice(1, -1)
  s = s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, '&')
  s = s.replace(/\\(['"@?n t\\])/g, (_, c) => (c === 'n' ? '\n' : c === 't' ? '\t' : c))
  // Positional format arguments become {1}, {2}, … ; a literal %% is %.
  s = s.replace(/%(\d)\$[sd]/g, '{$1}').replace(/%%/g, '%')
  return s
}

/**
 * Refuse an apostrophe Android's resource compiler would reject.
 *
 * aapt2 fails the whole Android build on a bare `'` outside a quoted
 * string, and the Android build cannot run everywhere the web check does.
 * Failing here moves that error from CI to the first local `npm run check`.
 */
function refuseBareApostrophe(file, name, raw) {
  const s = raw.trim()
  if (s.startsWith('"') && s.endsWith('"')) return
  if (/(^|[^\\])'/.test(s)) {
    throw new Error(`${file}: string "${name}" has an unescaped apostrophe; write \\' instead`)
  }
}

/** Parse one strings.xml into { name: text | { one, other } }. */
function parse(file) {
  const xml = readFileSync(file, 'utf8').replace(/<!--[\s\S]*?-->/g, '')
  const out = {}
  for (const m of xml.matchAll(/<string\s+name="([^"]+)"[^>]*>([\s\S]*?)<\/string>/g)) {
    refuseBareApostrophe(file, m[1], m[2])
    out[m[1]] = decode(m[2])
  }
  for (const m of xml.matchAll(/<plurals\s+name="([^"]+)"[^>]*>([\s\S]*?)<\/plurals>/g)) {
    const forms = {}
    for (const item of m[2].matchAll(/<item\s+quantity="([^"]+)"\s*>([\s\S]*?)<\/item>/g)) {
      forms[item[1]] = decode(item[2])
    }
    out[m[1]] = forms
  }
  return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)))
}

/** Read `"server.key" to R.string.name` pairs out of MessageKeys.kt. */
function messageKeys() {
  const kt = readFileSync(
    join(repo, 'android/src/main/kotlin/com/shikkhokplus/app/feature/auth/MessageKeys.kt'),
    'utf8',
  )
  const out = {}
  for (const m of kt.matchAll(/"([a-z0-9_.]+)"\s+to\s+R\.string\.([a-z0-9_]+)/g)) {
    out[m[1]] = m[2]
  }
  return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)))
}

export function generate() {
  return {
    'strings.en.json': parse(join(res, 'values', 'strings.xml')),
    'strings.bn.json': parse(join(res, 'values-bn', 'strings.xml')),
    'message-keys.json': messageKeys(),
  }
}

export function serialise(value) {
  return JSON.stringify(value, null, 2) + '\n'
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  mkdirSync(outDir, { recursive: true })
  for (const [name, value] of Object.entries(generate())) {
    writeFileSync(join(outDir, name), serialise(value))
  }
  console.log(`wrote ${outDir}`)
}
