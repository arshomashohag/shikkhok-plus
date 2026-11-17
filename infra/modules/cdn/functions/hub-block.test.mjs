// The API distribution's /hub* function (hub-block.js), run as written.
// Zero dependencies: `make infra-functions`.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const handler = new Function(
  `${readFileSync(resolve(HERE, 'hub-block.js'), 'utf8')}\nreturn handler;`,
)();

const event = (method, uri) => ({
  request: { method, uri, querystring: {}, headers: {}, cookies: {} },
});

describe('hub-block (on /hub* of the API host)', () => {
  for (const [method, uri] of [
    ['GET', '/hub'],
    ['GET', '/hub/en'],
    ['GET', '/hub/bn/t/some-owner/some-batch'],
    ['GET', '/hub/sitemap.xml'],
    ['HEAD', '/hub/en'],
    ['POST', '/hub/en'],
    ['GET', '/hubness'],
  ]) {
    it(`answers ${method} ${uri} with an empty 404 and never forwards it`, () => {
      const r = handler(event(method, uri));
      assert.equal(r.statusCode, 404);
      assert.equal(r.uri, undefined, 'a request object would reach the origin');
      assert.equal(r.body, undefined);
    });
  }
});
