// @vitest-environment node
/**
 * The lint configuration that keeps identifiers out of the console, pinned
 * [NFR3.5] [TSD-2].
 *
 * `no-console` deleted from `eslint.config.js` would otherwise vanish with
 * a green lint, and an inline directive is a way round any rule. So this
 * resolves the configuration through ESLint's own Node API, and compares
 * every inline ESLint directive under `src` with an exact committed list.
 *
 * Limits, stated plainly: the scan is textual, so a directive assembled to
 * dodge the pattern (split across lines inside a block comment, say) is
 * review's; and line numbers are deliberately not pinned, so a directive
 * that moves with its code does not fail this.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { ESLint } from 'eslint'
import { describe, expect, it } from 'vitest'

const ROOT = process.cwd()

/** The pattern of security NFR3.5: any ESLint inline directive or config comment. */
const DIRECTIVE =
  /(\/\/|\/\*)\s*(eslint(-disable(-next-line|-line)?|-enable)?|globals?|exported)(\s|\*\/|$)/

/** Excluded from the scan, as lint ignores them: generated, not written. */
const GENERATED = ['src/api/schema.d.ts', 'src/i18n/generated']

/**
 * Every inline directive allowed under `src`, as (file, directive text):
 * the two `react-hooks/exhaustive-deps` exemptions that predate this unit,
 * and the two annotated `no-console` exemptions it adds. A change here is
 * a change review sees in the same diff.
 */
const NO_CONSOLE_REASON =
  'a client bug, not a server answer: kept visible to the developer; it carries a thrown error, never a typed value'
const ALLOWED: [string, string][] = [
  ['src/core/useResource.ts', `// eslint-disable-next-line no-console -- ${NO_CONSOLE_REASON}`],
  ['src/core/useResource.ts', '// eslint-disable-next-line react-hooks/exhaustive-deps'],
  [
    'src/features/family/pay/PayScreen.tsx',
    `// eslint-disable-next-line no-console -- ${NO_CONSOLE_REASON}`,
  ],
  ['src/ui/components.tsx', '// eslint-disable-next-line react-hooks/exhaustive-deps'],
]

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    const rel = relative(ROOT, path).split('\\').join('/')
    if (GENERATED.some((g) => rel === g || rel.startsWith(`${g}/`))) return []
    if (entry.isDirectory()) return sourceFiles(path)
    if (!/\.(ts|tsx)$/.test(entry.name) || /\.test\.(ts|tsx)$/.test(entry.name)) return []
    return [rel]
  })
}

/** (file, directive) → count. */
function directives(): Map<string, number> {
  const found = new Map<string, number>()
  for (const file of sourceFiles(join(ROOT, 'src'))) {
    for (const line of readFileSync(join(ROOT, file), 'utf8').split('\n')) {
      const match = DIRECTIVE.exec(line)
      if (!match) continue
      const key = `${file} :: ${line.slice(match.index).trim()}`
      found.set(key, (found.get(key) ?? 0) + 1)
    }
  }
  return found
}

function severity(rule: unknown): unknown {
  return Array.isArray(rule) ? rule[0] : rule
}

describe('no-console [NFR3.5]', () => {
  const eslint = new ESLint({ cwd: ROOT })

  it('is an error, with no allowed method, on shipped source', async () => {
    for (const file of ['src/App.tsx', 'src/features/auth/SignUp.tsx', 'src/api/client.ts']) {
      const config = (await eslint.calculateConfigForFile(file)) as {
        rules: Record<string, unknown>
      }
      const rule = config.rules['no-console']
      expect([2, 'error']).toContain(severity(rule))
      // No `allow` list or other option: every method is refused.
      const options = Array.isArray(rule) ? (rule.slice(1) as object[]) : []
      expect(options.filter((o) => Object.keys(o).length > 0)).toEqual([])
    }
  })

  it('does not apply to tests, which may spy on the console', async () => {
    for (const file of ['src/api/client.test.ts', 'src/test/render.tsx']) {
      const config = (await eslint.calculateConfigForFile(file)) as {
        rules: Record<string, unknown>
      }
      expect([undefined, 0, 'off']).toContain(severity(config.rules['no-console']))
    }
  })

  it('reports a directive that suppresses nothing', async () => {
    const config = (await eslint.calculateConfigForFile('src/App.tsx')) as {
      linterOptions?: { reportUnusedDisableDirectives?: unknown }
    }
    expect([2, 'error']).toContain(config.linterOptions?.reportUnusedDisableDirectives)
  })

  it('fails a console call planted in shipped source, and passes it in a test', async () => {
    const planted = 'export function f(x: string): void {\n  console.info(x)\n}\n'
    const [shipped] = await eslint.lintText(planted, { filePath: join(ROOT, 'src/planted.ts') })
    expect(shipped!.messages.map((m) => m.ruleId)).toContain('no-console')
    const [test] = await eslint.lintText(planted, { filePath: join(ROOT, 'src/planted.test.ts') })
    expect(test!.messages.map((m) => m.ruleId)).not.toContain('no-console')
  })
})

describe('inline ESLint directives under src are pinned [NFR3.5]', () => {
  it('the scan sees source files at all', () => {
    const files = sourceFiles(join(ROOT, 'src'))
    expect(files).toContain('src/App.tsx')
    expect(files).toContain('src/core/useResource.ts')
    expect(files).not.toContain('src/api/schema.d.ts')
    expect(files.some((f) => f.endsWith('.test.ts') || f.endsWith('.test.tsx'))).toBe(false)
  })

  it('the pattern catches every directive shape, and not ordinary comments', () => {
    for (const shape of [
      '// eslint-disable-next-line',
      '/* eslint-disable */',
      '// eslint-disable-line no-console',
      '/* eslint no-console: off */',
      '/* global indexedDB */',
      '/* exported f */',
      '// eslint-enable',
    ])
      expect(DIRECTIVE.test(shape), shape).toBe(true)
    for (const prose of ['// eslintish', '// globalstate', '// exporter', '// plain words'])
      expect(DIRECTIVE.test(prose), prose).toBe(false)
  })

  it('matches the committed list exactly, as a multiset', () => {
    const expected = new Map<string, number>()
    for (const [file, text] of ALLOWED) {
      const key = `${file} :: ${text}`
      expected.set(key, (expected.get(key) ?? 0) + 1)
    }
    expect(Object.fromEntries(directives())).toEqual(Object.fromEntries(expected))
  })
})
