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

  it('lowercases subject and level', () => {
    const r = handler(event('/hub/en', { subject: one('PhYsics'), level: one('SSC') }));
    assert.equal(r.querystring.subject.value, 'physics');
    assert.equal(r.querystring.level.value, 'ssc');
  });

  // Area codes are uppercase (BD3026, BD30262500, MT3026250003) and the
  // origin compares them exactly, so lowercasing them here made every
  // area filter match nothing through CloudFront.
  it('leaves district and upazila codes as sent', () => {
    const r = handler(
      event('/hub/en', { district: one('BD3026'), upazila: one('MT3026250003') }),
    );
    assert.equal(r.querystring.district.value, 'BD3026');
    assert.equal(r.querystring.upazila.value, 'MT3026250003');
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

describe('hub-query: percent-encoded input', () => {
  const bangla = 'ঢাকা'; // Dhaka
  const enc = encodeURIComponent;

  it('truncates a long Bangla q by characters, not mid-escape', () => {
    const long = bangla.repeat(15); // 60 code points, 540 encoded chars
    const longer = (bangla + ' ').repeat(60); // 300 code points
    const r = handler(event('/hub/en', { q: one(enc(long + longer)) }));
    assert.equal(r.statusCode, undefined);
    const decoded = decodeURIComponent(r.querystring.q.value);
    assert.equal(Array.from(decoded).length, 200);
    assert.equal(decoded, Array.from(long + longer).slice(0, 200).join(''));
  });

  it('does not double-encode on the redirect and turns + into a space', () => {
    const r = handler(event('/hub', { q: one(`${enc(bangla)}+physics`), level: one('SSC') }));
    assert.equal(r.statusCode, 301);
    assert.equal(r.headers.location.value, `/hub/en?q=${enc(bangla + ' physics')}&level=ssc`);
  });

  it('keeps an area code uppercase across the redirect', () => {
    const r = handler(event('/hub', { district: one('BD3026') }));
    assert.equal(r.headers.location.value, '/hub/en?district=BD3026');
  });

  it('forwards decoded-then-reencoded values', () => {
    const r = handler(event('/hub/en', { q: one('a+b%26c') }));
    assert.equal(r.querystring.q.value, 'a%20b%26c');
  });

  it('lowercases after decoding', () => {
    const r = handler(event('/hub/en', { subject: one('%50HYSICS') }));
    assert.equal(r.querystring.subject.value, 'physics');
  });

  for (const bad of ['%E', '%E0%A6', '100%']) {
    it(`answers 400 for malformed escape ${bad}`, () => {
      assert.equal(handler(event('/hub/en', { q: one(bad) })).statusCode, 400);
      assert.equal(handler(event('/hub', { district: one(bad) })).statusCode, 400);
    });
  }

  it('keeps the first value of a repeated encoded key', () => {
    const r = handler(event('/hub/en', { q: many(enc(bangla), 'x') }));
    assert.equal(r.querystring.q.value, enc(bangla));
  });
});
