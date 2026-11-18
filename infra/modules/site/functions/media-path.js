// Viewer-request function on the site distribution's /m/* behaviour.
//
// A hub photo's public URL is /m/{public_key}/{width}.webp on the site
// host; the object is public/{public_key}/{width}.webp in the media bucket
// (infra/modules/media). CloudFront's origin path can only PREPEND to the
// request path -- /m/k/320.webp with origin path /public would fetch
// public/m/k/320.webp -- so the /m/ to /public/ step is made here.
//
// **Exactly one shape is mapped, and everything else is 404 at the edge**:
// a 32-character lowercase hex key (secrets.token_hex(16)) and a numeric
// width, nothing between them. So no request through /m/ can name a dot
// segment, a nested path or any other prefix of the bucket -- the bucket
// policy already lets CloudFront read public/* only, and this keeps the
// viewer from even asking. The refusal carries nosniff itself, because a
// response a function generates is not an origin response.
//
// Not the site router: no www redirect and no directory index applies to
// an image. cloudfront-js-2.0 runtime; tested by media-path.test.mjs beside
// it (`make infra-functions`).
var MEDIA = /^\/m\/([0-9a-f]{32})\/([1-9][0-9]{1,3})\.webp$/;

function handler(event) {
  var request = event.request;
  var match = MEDIA.exec(request.uri);
  if (!match) {
    return {
      statusCode: 404,
      statusDescription: 'Not Found',
      headers: {
        'x-content-type-options': { value: 'nosniff' },
        'cache-control': { value: 'public, max-age=60' },
      },
    };
  }
  request.uri = '/public/' + match[1] + '/' + match[2] + '.webp';
  return request;
}
