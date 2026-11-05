// Viewer-request function for the web client's paths (/ui and /ui/*).
//
// The web client is a single-page app: /ui/dues, /ui/batches/<id> and
// every other screen are routes inside index.html, not files in the
// bucket. S3 would answer them 403 (a private bucket hides whether a key
// exists), so a path with no file extension is served index.html and
// the app's router takes it from there. A path WITH an extension is a
// real file and goes to S3 unchanged, so a missing asset is still an
// error rather than a page.
//
// /ui with no slash is redirected to /ui/, which is the scope the
// service worker and the manifest were built for.
//
// cloudfront-js-2.0 runtime. Kept free of anything the runtime lacks,
// and tested from web/src/deploy/ui-router.test.ts.
function handler(event) {
  var request = event.request;
  var uri = request.uri;

  if (uri === '/ui') {
    return {
      statusCode: 301,
      statusDescription: 'Moved Permanently',
      headers: { location: { value: '/ui/' } },
    };
  }

  var last = uri.substring(uri.lastIndexOf('/') + 1);
  if (last.indexOf('.') === -1) {
    request.uri = '/ui/index.html';
  }
  return request;
}
