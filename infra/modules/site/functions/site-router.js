// Viewer-request function for the public site's distribution.
//
// Two jobs, both of which S3 cannot do for a private bucket behind Origin
// Access Control (there is no static-website hosting to lean on):
//
//   1. **www. is an alias, not a second site.** A request for
//      www.<host> is answered 301 to the same path and query on <host>,
//      so search engines see one canonical address and the hreflang and
//      canonical links in every page agree with the URL bar. Derived from
//      the Host header rather than templated, so the function is the same
//      file in every environment and the unit test runs it as written.
//
//   2. **Directory indexes.** /faq/ is the object faq/index.html, which S3
//      would not find on its own -- it answers a missing key 403. A path
//      ending in "/" gets index.html appended; a path whose last segment
//      has no dot (/faq, /bn) is redirected to the slash form first, so a
//      page has exactly one URL and relative behaviour matches the
//      canonical link. A path with a dot is a real file and goes to S3
//      unchanged, so a missing asset is still a 404 rather than a page.
//
// cloudfront-js-2.0 runtime. Kept free of anything the runtime lacks, and
// tested from site/test/site-router.test.mjs.
function queryString(querystring) {
  var parts = [];
  for (var key in querystring) {
    var entry = querystring[key];
    var values = entry.multiValue ? entry.multiValue : [entry];
    for (var i = 0; i < values.length; i++) {
      var value = values[i].value;
      parts.push(value === '' ? key : key + '=' + value);
    }
  }
  return parts.length ? '?' + parts.join('&') : '';
}

function redirect(location) {
  return {
    statusCode: 301,
    statusDescription: 'Moved Permanently',
    headers: { location: { value: location } },
  };
}

function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var host = request.headers.host ? request.headers.host.value.toLowerCase() : '';

  if (host.indexOf('www.') === 0) {
    return redirect('https://' + host.substring(4) + uri + queryString(request.querystring || {}));
  }

  if (uri.charAt(uri.length - 1) === '/') {
    request.uri = uri + 'index.html';
    return request;
  }

  var last = uri.substring(uri.lastIndexOf('/') + 1);
  if (last.indexOf('.') === -1) {
    return redirect(uri + '/' + queryString(request.querystring || {}));
  }
  return request;
}
