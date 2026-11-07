// Viewer-request function on the API distribution's /v1/admin* behaviour.
//
// **The admin API is not served from the public API host.** It is reachable
// only through the admin hostname (infra/modules/admin), whose distribution
// checks the viewer's IP against an allowlist and adds the X-Admin-Edge
// header the application requires on every admin route. This function is
// the API host's half: every request whose path matches /v1/admin* is
// answered 404 at the edge, whatever its method, and never reaches the
// origin.
//
// **Two independent locks.** If this behaviour were ever removed, the
// application would still refuse an admin route that arrives without the
// X-Admin-Edge value only the admin distribution sends. If the
// application's check regressed, this still stops the request at the
// edge. Either one alone keeps the admin API off the public host.
//
// 404 rather than 403: from this host the routes do not exist, and saying
// "forbidden" would confirm that they do. no-store, so no cache between
// here and the client keeps even the refusal.
//
// cloudfront-js-2.0 runtime. Tested by admin-block.test.mjs beside it
// (`make infra-functions`).
function handler(event) {
  return {
    statusCode: 404,
    statusDescription: 'Not Found',
    headers: {
      'content-type': { value: 'text/plain; charset=utf-8' },
      'cache-control': { value: 'no-store' },
    },
    body: { encoding: 'text', data: 'Not found.\n' },
  };
}
