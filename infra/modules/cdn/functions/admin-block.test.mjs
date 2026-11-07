// The API distribution's /v1/admin* function (admin-block.js), run as
// written. Zero dependencies: `make infra-functions`.
//
// The web client's tests for this directory's other two functions live in
// web/src/deploy/cloudfront-functions.test.ts; this one sits here so the
// infra change needs no web change.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const handler = new Function(
  `${readFileSync(resolve(HERE, 'admin-block.js'), 'utf8')}\nreturn handler;`,
)();

function event(method, uri, headers = {}) {
  return {
    viewer: { ip: '192.0.2.1' },
    request: {
      method,
      uri,
      querystring: {},
      headers: { host: { value: 'api.shikkhokplus.example.com' }, ...headers },
      cookies: {},
    },
  };
}

describe('admin-block (on /v1/admin* of the API host)', () => {
  for (const [method, uri] of [
    ['GET', '/v1/admin/overview'],
    ['GET', '/v1/admin/teachers'],
    ['POST', '/v1/admin/help/tickets/abc/messages'],
    ['PUT', '/v1/admin/help/tickets/abc/status'],
    ['GET', '/v1/admin'],
  ]) {
    it(`answers ${method} ${uri} with 404 and never forwards it`, () => {
      const result = handler(event(method, uri));
      assert.equal(result.statusCode, 404);
      assert.equal(result.uri, undefined, 'a request object would reach the origin');
      assert.equal(result.headers['cache-control'].value, 'no-store');
    });
  }

  it('is not opened by a viewer presenting X-Admin-Edge', () => {
    const result = handler(event('GET', '/v1/admin/overview', { 'x-admin-edge': { value: 'guess' } }));
    assert.equal(result.statusCode, 404);
  });
});
