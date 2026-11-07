// The admin distribution's viewer-request function (admin-gate.js.tftpl),
// rendered the way Terraform renders it and run as written.
//
// Zero dependencies: `node --test infra/modules/admin/functions/`, or
// `make infra-functions`, which runs this beside the API distribution's
// admin-block test.
//
// The property that matters most: a viewer outside the allowlist gets a
// 403 on every path, and an empty allowlist lets nobody in.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const TEMPLATE = readFileSync(resolve(HERE, 'admin-gate.js.tftpl'), 'utf8');
const PLACEHOLDER = '${allowed_cidrs_json}';

// What templatefile() does with `allowed_cidrs_json = jsonencode(list)`.
function load(cidrs) {
  const source = TEMPLATE.replace(PLACEHOLDER, JSON.stringify(cidrs));
  return new Function(`${source}\nreturn handler;`)();
}

function event(uri, ip, headers = {}) {
  return {
    viewer: { ip },
    request: {
      method: 'GET',
      uri,
      querystring: {},
      headers: { host: { value: 'admin.shikkhokplus.example.com' }, ...headers },
      cookies: {},
    },
  };
}

function isDenied(result) {
  return result.statusCode === 403;
}

describe('the template', () => {
  it('has exactly one placeholder and nothing else Terraform would interpolate', () => {
    // templatefile() treats every dollar-brace and percent-brace as its
    // own syntax; a stray one fails the apply or, worse, renders.
    assert.equal(TEMPLATE.split('${').length - 1, 1);
    assert.ok(TEMPLATE.includes(PLACEHOLDER));
    assert.ok(!TEMPLATE.includes('%{'));
  });
});

describe('the IP allowlist', () => {
  const handler = load(['203.0.113.7/32', '198.51.100.0/24']);

  it('lets an exact /32 in', () => {
    assert.ok(!isDenied(handler(event('/', '203.0.113.7'))));
  });

  it('refuses the neighbours of a /32', () => {
    assert.ok(isDenied(handler(event('/', '203.0.113.6'))));
    assert.ok(isDenied(handler(event('/', '203.0.113.8'))));
  });

  it('lets every address of a /24 in, and nothing either side of it', () => {
    assert.ok(!isDenied(handler(event('/', '198.51.100.0'))));
    assert.ok(!isDenied(handler(event('/', '198.51.100.129'))));
    assert.ok(!isDenied(handler(event('/', '198.51.100.255'))));
    assert.ok(isDenied(handler(event('/', '198.51.99.255'))));
    assert.ok(isDenied(handler(event('/', '198.51.101.0'))));
  });

  it('refuses everyone else, on the UI and on the API path alike', () => {
    for (const uri of ['/', '/teachers', '/assets/index-abc.js', '/v1/admin/overview']) {
      const result = handler(event(uri, '192.0.2.1'));
      assert.equal(result.statusCode, 403, uri);
      assert.equal(result.body.data, 'Not available from this network.\n');
      assert.equal(result.headers['cache-control'].value, 'no-store');
    }
  });

  it('handles the top of the address space without sign trouble', () => {
    // 255.x is above 2^31: a signed comparison would get this wrong.
    const high = load(['255.255.255.0/24']);
    assert.ok(!isDenied(high(event('/', '255.255.255.254'))));
    assert.ok(isDenied(high(event('/', '255.255.254.255'))));
    const mid = load(['128.0.0.0/1']);
    assert.ok(!isDenied(mid(event('/', '200.1.2.3'))));
    assert.ok(isDenied(mid(event('/', '127.255.255.255'))));
  });

  it('treats /0 as everyone with an IPv4 address', () => {
    const open = load(['0.0.0.0/0']);
    for (const ip of ['0.0.0.0', '1.2.3.4', '192.0.2.1', '255.255.255.255']) {
      assert.ok(!isDenied(open(event('/', ip))), ip);
    }
  });

  it('accepts a CIDR whose host bits are set, as cidrhost() does', () => {
    const loose = load(['10.1.2.3/16']);
    assert.ok(!isDenied(loose(event('/', '10.1.200.200'))));
    assert.ok(isDenied(loose(event('/', '10.2.0.1'))));
  });

  it('lets nobody in when the list is empty', () => {
    const closed = load([]);
    for (const ip of ['203.0.113.7', '127.0.0.1', '0.0.0.0', '255.255.255.255']) {
      assert.ok(isDenied(closed(event('/', ip))), ip);
      assert.ok(isDenied(closed(event('/v1/admin/overview', ip))), ip);
    }
  });

  it('refuses an address that is not a dotted quad, IPv6 included', () => {
    const open = load(['0.0.0.0/0']);
    for (const ip of [undefined, '', '2001:db8::1', '::ffff:1.2.3.4', '1.2.3', '1.2.3.4.5', '1.2.3.256', '01.2.3.4444', 'a.b.c.d']) {
      assert.ok(isDenied(open(event('/', ip))), String(ip));
    }
  });

  it('ignores a malformed entry rather than widening to it', () => {
    const odd = load(['nonsense', '10.0.0.0/33', '203.0.113.7/32']);
    assert.ok(!isDenied(odd(event('/', '203.0.113.7'))));
    assert.ok(isDenied(odd(event('/', '10.0.0.1'))));
  });
});

describe('routing for an allowed viewer', () => {
  const handler = load(['203.0.113.0/24']);
  const ip = '203.0.113.10';

  for (const uri of ['/', '/teachers', '/help/tickets/93eb0d57-6a0b-4f87-8067-86298f00ae45', '/signin']) {
    it(`serves index.html for the client route ${uri}`, () => {
      assert.equal(handler(event(uri, ip)).uri, '/index.html');
    });
  }

  for (const uri of ['/index.html', '/assets/x.js', '/assets/index-Iyq8Vukz.css', '/favicon.ico']) {
    it(`passes the real file ${uri} to S3 unchanged`, () => {
      assert.equal(handler(event(uri, ip)).uri, uri);
    });
  }

  it('passes the admin API through unchanged', () => {
    for (const uri of ['/v1/admin/overview', '/v1/admin/help/tickets/abc/messages']) {
      assert.equal(handler(event(uri, ip)).uri, uri);
    }
  });

  it('answers 404 for any other API path: this host serves the admin API only', () => {
    for (const uri of ['/v1/me', '/v1/auth/otp', '/v1/', '/v1/administrators']) {
      const result = handler(event(uri, ip));
      assert.equal(result.statusCode, 404, uri);
      assert.equal(result.headers['cache-control'].value, 'no-store');
    }
  });
});

describe('X-Admin-Edge from a viewer', () => {
  it('is dropped before the request goes anywhere', () => {
    const handler = load(['203.0.113.0/24']);
    const result = handler(
      event('/v1/admin/overview', '203.0.113.10', { 'x-admin-edge': { value: 'guess' } }),
    );
    assert.equal(result.uri, '/v1/admin/overview');
    assert.equal(result.headers['x-admin-edge'], undefined);
    assert.equal(result.headers.host.value, 'admin.shikkhokplus.example.com');
  });

  it('does not open the gate to a viewer outside the list', () => {
    const handler = load(['203.0.113.0/24']);
    const result = handler(
      event('/v1/admin/overview', '192.0.2.1', { 'x-admin-edge': { value: 'the-real-secret' } }),
    );
    assert.equal(result.statusCode, 403);
  });
});
