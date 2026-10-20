"""HTTP boundary shared by signed probes and Demo-only validation."""

from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "redirect forbidden", headers, fp)


def secure_open(request, *, timeout, context):
    return build_opener(RejectRedirects(), HTTPSHandler(context=context)).open(
        request, timeout=timeout
    )
