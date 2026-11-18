// A guard for the CloudFront Functions JavaScript runtime 2.0 feature set.
//
// These functions are tested under Node, which supports far more than the
// edge runtime does, so a call the runtime lacks passes every behavioural
// test and throws at the edge. This is a SIMPLE DENYLIST of constructs
// likely to slip in, mirroring AWS's "JavaScript runtime 2.0 features for
// CloudFront Functions" page (Array offers only isArray and of; statements
// are ES5.1 plus const/let/async/await; no for-of, no spread beyond rest
// parameters). It is NOT exhaustive: a clean run proves only that none of
// these appear.
//
// It scans every function under infra/modules/*/functions/, with comments
// and string literals blanked first so prose cannot trip it.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const MODULES = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

const DENY = [
  [/\bArray\.from\b/, 'Array.from'],
  [/\bfor\s*\([^)]*\bof\b/, 'for (... of ...)'],
  [/\.\.\./, 'spread / rest syntax (...)'],
  [/\bObject\.fromEntries\b/, 'Object.fromEntries'],
  [/\?\./, 'optional chaining (?.)'],
  [/\?\?/, 'nullish coalescing (??)'],
  [/\bnew\s+Set\b/, 'new Set'],
  [/\bnew\s+Map\b/, 'new Map'],
];

/** Blank comments and string literals, keeping newlines so line numbers hold. */
function blank(src) {
  return src.replace(
    /\/\*[\s\S]*?\*\/|\/\/[^\n]*|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`/g,
    (m) => m.replace(/[^\n]/g, ' '),
  );
}

function functionFiles() {
  const out = [];
  for (const mod of readdirSync(MODULES, { withFileTypes: true })) {
    if (!mod.isDirectory()) continue;
    const dir = join(MODULES, mod.name, 'functions');
    let names = [];
    try {
      names = readdirSync(dir);
    } catch {
      continue;
    }
    for (const n of names) {
      if (/\.js(\.tftpl)?$/.test(n)) out.push(join(dir, n));
    }
  }
  return out;
}

describe('CloudFront Functions runtime 2.0 denylist', () => {
  const files = functionFiles();

  it('finds the functions it is meant to scan', () => {
    const names = files.map((f) => f.split('/').pop());
    for (const n of ['hub-query.js', 'hub-block.js', 'site-router.js', 'admin-block.js']) {
      assert.ok(names.includes(n), `${n} not scanned`);
    }
  });

  it('flags what it claims to flag', () => {
    const bad = blank('var a = Array.from(x); for (var k of y) {} f(...z); a?.b; a ?? b;');
    const hits = DENY.filter(([re]) => re.test(bad)).map(([, name]) => name);
    assert.equal(hits.length, 5);
  });

  for (const file of files) {
    it(`${file.split('/').slice(-3).join('/')} uses none of them`, () => {
      const lines = blank(readFileSync(file, 'utf8')).split('\n');
      const found = [];
      lines.forEach((line, i) => {
        for (const [re, name] of DENY) {
          if (re.test(line)) found.push(`${file}:${i + 1}: ${name}`);
        }
      });
      assert.deepEqual(found, []);
    });
  }
});
