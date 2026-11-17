// The site distribution's /hub/* viewer-request function (hub-query.js),
// run as written. Zero dependencies: `make infra-functions`.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const handler = new Function(
  `${readFileSync(resolve(HERE, 'hub-query.js'), 'utf8')}\nreturn handler;`,
)();

// cloudfront-js-2.0 shape: `value` is the first value, `multiValue` (only
// when the key repeats) lists them all.
function event(uri, qs = {}) {
  return { request: { method: 'GET', uri, querystring: qs, headers: {} } };
}
const one = (value) => ({ value });
const many = (...values) => ({ value: values[0], multiValue: values.map((value) => ({ value })) });

describe('hub-query: query-string allowlist', () => {
  it('answers 400 for an unknown key and never forwards it', () => {
    const r = handler(event('/hub/en', { utm_source: one('x') }));
    assert.equal(r.statusCode, 400);
    assert.equal(r.uri, undefined);
  });

  it('answers 400 when one unknown key sits among allowed ones', () => {
    const r = handler(event('/hub/en', { q: one('a'), fbclid: one('x') }));
    assert.equal(r.statusCode, 400);
  });

  it('passes every allowed key through', () => {
    const qs = {
      q: one('math'),
      district: one('dhaka'),
      upazila: one('mirpur'),
      subject: one('physics'),
      level: one('ssc'),
      page: one('2'),
    };
    const r = handler(event('/hub/en', qs));
    assert.equal(r.uri, '/hub/en');
    assert.deepEqual(Object.keys(r.querystring).sort(), Object.keys(qs).sort());
    assert.equal(r.querystring.page.value, '2');
    assert.equal(r.querystring.q.value, 'math');
  });

  it('passes a request with no query string', () => {
    const r = handler(event('/hub/bn/t/some-owner'));
    assert.equal(r.uri, '/hub/bn/t/some-owner');
  });
});

describe('hub-query: normalisation', () => {
  it('keeps the first value of a repeated key', () => {
    const r = handler(event('/hub/en', { q: many('a', 'b') }));
    assert.equal(r.querystring.q.value, 'a');
    assert.equal(r.querystring.q.multiValue, undefined);
  });

  it('keeps the first value of a repeated page', () => {
    const r = handler(event('/hub/en', { page: many('2', '9') }));
    assert.equal(r.querystring.page.value, '2');
  });

  it('lowercases district, upazila, subject and level', () => {
    const r = handler(
      event('/hub/en', {
        district: one('DHAKA'),
        upazila: one('Mirpur'),
        subject: one('PhYsics'),
        level: one('SSC'),
      }),
    );
    assert.equal(r.querystring.district.value, 'dhaka');
    assert.equal(r.querystring.upazila.value, 'mirpur');
    assert.equal(r.querystring.subject.value, 'physics');
    assert.equal(r.querystring.level.value, 'ssc');
  });

  it('does not lowercase q', () => {
    const r = handler(event('/hub/en', { q: one('Math') }));
    assert.equal(r.querystring.q.value, 'Math');
  });

  it('truncates q to 200 characters', () => {
    const r = handler(event('/hub/en', { q: one('x'.repeat(500)) }));
    assert.equal(r.querystring.q.value.length, 200);
  });

  it('leaves a 200-character q alone', () => {
    const r = handler(event('/hub/en', { q: one('y'.repeat(200)) }));
    assert.equal(r.querystring.q.value, 'y'.repeat(200));
  });
});

describe('hub-query: the bare /hub', () => {
  for (const uri of ['/hub', '/hub/']) {
    it(`301s ${uri} to /hub/en`, () => {
      const r = handler(event(uri));
      assert.equal(r.statusCode, 301);
      assert.equal(r.headers.location.value, '/hub/en');
    });
  }

  it('keeps an allowed query string across the redirect', () => {
    const r = handler(event('/hub', { q: one('math') }));
    assert.equal(r.statusCode, 301);
    assert.equal(r.headers.location.value, '/hub/en?q=math');
  });

  it('does not redirect other paths', () => {
    const r = handler(event('/hub/sitemap.xml'));
    assert.equal(r.statusCode, undefined);
    assert.equal(r.uri, '/hub/sitemap.xml');
  });
});
