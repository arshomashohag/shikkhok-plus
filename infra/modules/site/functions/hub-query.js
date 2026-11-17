// Viewer-request function on the site distribution's /hub/* behaviour.
//
// The origin (the API) ignores every query key outside its allowlist, but
// a cache key built from the raw query string would still let a crawler
// mint endless distinct cache entries (?utm_source=1, ?utm_source=2, ...).
// So the edge refuses unknown keys outright and normalises the rest, which
// keeps the cache-key space bounded by the six allowed keys:
//
//   * a key outside q, district, upazila, subject, level, page -> 400
//   * a repeated key keeps its FIRST value
//   * subject and level are lowercased; district and upazila are not,
//     because they are uppercase area codes (BD3026, MT3026250003) the
//     origin matches exactly
//   * q is truncated to 200 characters
//   * /hub and /hub/ -> 301 /hub/en (query string kept)
//
// Values are normalised DECODED and re-encoded: CloudFront hands the
// function a UTF-8 percent-encoded value unchanged (AWS, "Restrictions on
// all edge functions"), so each value is decoded ('+' is a space, then
// decodeURIComponent), lowercased / truncated by code point on the decoded
// string (never mid-escape, never mid-character), and encoded again with
// encodeURIComponent for both the forwarded value and the Location header.
// A malformed escape (e.g. a trailing %E) gets 400.
//
// Everything else passes through untouched. cloudfront-js-2.0 runtime:
// `value` is the first value of a key and `multiValue` lists all of them
// when it repeats. Tested by hub-query.test.mjs beside it
// (`make infra-functions`).
var ALLOWED = ['q', 'district', 'upazila', 'subject', 'level', 'page'];
var LOWERCASED = ['subject', 'level'];
var Q_MAX = 200;

function handler(event) {
  var request = event.request;
  var incoming = request.querystring || {};
  var clean = {};
  var parts = [];

  for (var key in incoming) {
    if (ALLOWED.indexOf(key) === -1) {
      return { statusCode: 400, statusDescription: 'Bad Request' };
    }
    var entry = incoming[key];
    var raw = entry.multiValue && entry.multiValue.length ? entry.multiValue[0].value : entry.value;
    raw = raw === undefined || raw === null ? '' : String(raw);
    var value;
    try {
      value = decodeURIComponent(raw.replace(/\+/g, ' '));
    } catch (e) {
      return { statusCode: 400, statusDescription: 'Bad Request' };
    }
    if (LOWERCASED.indexOf(key) !== -1) {
      value = value.toLowerCase();
    }
    if (key === 'q') {
      // By code point, without Array.from (absent from the CloudFront
      // Functions 2.0 runtime): an astral character is two UTF-16 units.
      var i = 0;
      var count = 0;
      while (i < value.length && count < Q_MAX) {
        i += value.codePointAt(i) > 0xffff ? 2 : 1;
        count += 1;
      }
      value = value.slice(0, i);
    }
    var encoded = encodeURIComponent(value);
    clean[key] = { value: encoded };
    parts.push(key + '=' + encoded);
  }

  if (request.uri === '/hub' || request.uri === '/hub/') {
    var qs = parts.join('&');
    return {
      statusCode: 301,
      statusDescription: 'Moved Permanently',
      headers: { location: { value: '/hub/en' + (qs ? '?' + qs : '') } },
    };
  }

  request.querystring = clean;
  return request;
}
