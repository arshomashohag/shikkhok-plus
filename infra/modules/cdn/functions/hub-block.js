// Viewer-request function on the API distribution's /hub* behaviour.
//
// **The public hub is served from the marketing site's distribution, not
// from the API host.** The site distribution puts /hub/* in front of the
// same origin, with the CDN cache and the query-string allowlist in front
// of it. This function is the API host's half: every request whose path
// matches /hub* is answered 404 at the edge, whatever its method, and never
// reaches the origin -- so the API host cannot be used to reach the hub
// pages around the cache, the allowlist and the rate-limit key.
//
// An empty body, no cache-control: a refusal that says nothing and that
// nothing downstream keeps. The pattern /hub* also matches /hubness; no API
// route starts with /hub, so nothing real is shadowed.
//
// cloudfront-js-2.0 runtime. Tested by hub-block.test.mjs beside it
// (`make infra-functions`).
function handler(event) {
  return {
    statusCode: 404,
    statusDescription: 'Not Found',
  };
}
