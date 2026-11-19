// The site distribution's /m/* viewer-request function (media-path.js),
// run as written. Zero dependencies: `make infra-functions`.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const handler = new Function(
  `${readFileSync(resolve(HERE, 'media-path.js'), 'utf8')}\nreturn handler;`,
)();

const KEY = '0123456789abcdef0123456789abcdef';

function event(uri) {
  return { request: { method: 'GET', uri, querystring: {}, headers: {} } };
}

describe('media-path: the public URL maps onto public/ only', () => {
  for (const width of ['320', '960', '1600']) {
    it(`maps /m/{key}/${width}.webp to /public/{key}/${width}.webp`, () => {
      const r = handler(event(`/m/${KEY}/${width}.webp`));
      assert.equal(r.uri, `/public/${KEY}/${width}.webp`);
      assert.equal(r.statusCode, undefined);
    });
  }

  const refused = [
    ['a key that is not 32 lowercase hex', `/m/${KEY.toUpperCase()}/320.webp`],
    ['a short key', '/m/abc/320.webp'],
    ['a dot segment', `/m/../${KEY}/320.webp`],
    ['an encoded dot segment', `/m/%2e%2e/${KEY}/320.webp`],
    ['another prefix spelled out', `/m/${KEY}/../../staged/${KEY}/320.webp`],
    ['a nested path', `/m/${KEY}/x/320.webp`],
    ['another extension', `/m/${KEY}/320.png`],
    ['no width', `/m/${KEY}/.webp`],
    ['a non-numeric width', `/m/${KEY}/result.json`],
    ['the bare prefix', '/m/'],
    ['a key directory', `/m/${KEY}/`],
    ['a width the sanitiser never writes', `/m/${KEY}/321.webp`],
    ['a four-digit width outside the three', `/m/${KEY}/9999.webp`],
    ['a zero-padded width', `/m/${KEY}/0320.webp`],
    ['an encoded slash', `/m/${KEY}%2F320.webp`],
    ['an encoded dot-dot and slash', `/m/${KEY}/%2e%2e%2F320.webp`],
  ];
  for (const [name, uri] of refused) {
    it(`answers 404 for ${name}, never reaching the bucket`, () => {
      const r = handler(event(uri));
      assert.equal(r.statusCode, 404);
      assert.equal(r.uri, undefined);
      assert.equal(r.headers['x-content-type-options'].value, 'nosniff');
    });
  }
});
