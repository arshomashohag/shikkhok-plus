// Fail when a generated file no longer matches its source.
//
// Three things in this client are copies of something owned elsewhere,
// and each would rot silently without this check:
//
//  * src/api/schema.d.ts      ← ../openapi.json (the committed contract)
//  * src/i18n/generated/*     ← the Android string bundles
//  * public/fonts/*.ttf       ← the Android app's bundled Noto fonts
//
// The same shape as the backend's OpenAPI schema-diff gate: the committed
// copy must equal what the generator produces now.

import { readFileSync, existsSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { generate, serialise } from './sync-strings.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const web = join(here, '..')
const repo = join(web, '..')
const problems = []

// 1. String bundles and the message-key map.
for (const [name, value] of Object.entries(generate())) {
  const file = join(web, 'src', 'i18n', 'generated', name)
  if (!existsSync(file) || readFileSync(file, 'utf8') !== serialise(value)) {
    problems.push(`src/i18n/generated/${name} is stale: run npm run gen:strings`)
  }
}

// 2. The API types, regenerated into memory and compared after formatting.
const fresh = execFileSync(
  'npx',
  ['--no-install', 'openapi-typescript', join(repo, 'openapi.json')],
  { cwd: web, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
)
const formatted = execFileSync(
  'npx',
  ['--no-install', 'prettier', '--stdin-filepath', 'src/api/schema.d.ts'],
  { cwd: web, input: fresh, encoding: 'utf8' },
)
if (readFileSync(join(web, 'src', 'api', 'schema.d.ts'), 'utf8') !== formatted) {
  problems.push('src/api/schema.d.ts does not match ../openapi.json: run npm run gen:api')
}

// 3. Fonts are byte-identical to Android's, so the two clients render the
//    same glyphs for the same Bangla text.
for (const weight of ['regular', 'medium', 'semibold', 'bold']) {
  const a = readFileSync(join(repo, 'android/src/main/res/font', `noto_${weight}.ttf`))
  const b = join(web, 'public/fonts', `noto_${weight}.ttf`)
  if (!existsSync(b) || !a.equals(readFileSync(b))) {
    problems.push(`public/fonts/noto_${weight}.ttf differs from the Android font`)
  }
}

if (problems.length) {
  console.error(problems.map((p) => `✗ ${p}`).join('\n'))
  process.exit(1)
}
console.log('✓ generated files are current')
