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
//   * district, upazila, subject, level are lowercased
//   * q is truncated to 200 characters
//   * /hub and /hub/ -> 301 /hub/en (query string kept)
//
// Everything else passes through untouched. cloudfront-js-2.0 runtime:
// `value` is the first value of a key and `multiValue` lists all of them
// when it repeats. Tested by hub-query.test.mjs beside it
// (`make infra-functions`).
var ALLOWED = ['q', 'district', 'upazila', 'subject', 'level', 'page'];
var LOWERCASED = ['district', 'upazila', 'subject', 'level'];
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
    var value = entry.multiValue && entry.multiValue.length ? entry.multiValue[0].value : entry.value;
    value = value === undefined || value === null ? '' : String(value);
    if (LOWERCASED.indexOf(key) !== -1) {
      value = value.toLowerCase();
    }
    if (key === 'q' && value.length > Q_MAX) {
      value = value.slice(0, Q_MAX);
    }
    clean[key] = { value: value };
    parts.push(key + '=' + value);
  }

  if (request.uri === '/hub' || request.uri === '/hub/') {
    // The values are already percent-decoded by CloudFront; encode them
    // again for the Location header.
    var qs = parts
      .map(function (p) {
        var i = p.indexOf('=');
        return p.slice(0, i) + '=' + encodeURIComponent(p.slice(i + 1));
      })
      .join('&');
    return {
      statusCode: 301,
      statusDescription: 'Moved Permanently',
      headers: { location: { value: '/hub/en' + (qs ? '?' + qs : '') } },
    };
  }

  request.querystring = clean;
  return request;
}
