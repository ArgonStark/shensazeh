from django.conf import settings

from .models import SiteSetting

_LOCAL_HOSTS = ('localhost', '127.0.0.1')


def _canonical_base(request):
    """Absolute origin for canonical/og:url tags, e.g. https://shensazeh.ir

    Deliberately taken from SITE_URL rather than the request: the site sits
    behind a CDN that terminates TLS and does not forward X-Forwarded-Proto, so
    request.scheme reports "http" on live traffic. A canonical tag pointing at
    http:// while the page is served over https:// splits the ranking signal
    between two URLs — the exact thing canonical exists to prevent.

    Falls back to the request when SITE_URL is still the local placeholder, so
    dev servers and tests describe themselves correctly.
    """
    base = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    if base and not any(host in base for host in _LOCAL_HOSTS):
        return base
    if request is not None:
        return f'{request.scheme}://{request.get_host()}'
    return base


DEFAULT_SEO_TITLE = 'شن‌سازه - ابزار و مصالح ساختمانی'
DEFAULT_SEO_DESCRIPTION = 'فروش ابزارآلات و مصالح ساختمانی'


def site_settings(request):
    """Expose the singleton SiteSetting to all templates as `site`."""
    context = {'canonical_base': _canonical_base(request)}
    try:
        context['site'] = SiteSetting.load()
    except Exception:
        # During initial migration the table may not exist yet.
        context['site'] = None

    # Resolved here rather than in the template so the SEO partial can use
    # {% with %} + |default. {% firstof ... as %} stores an *escaped* string,
    # which makes any filter applied afterwards a no-op — a page description
    # then ships raw "&lt;p&gt;" markup to search engines.
    site = context['site']
    context['seo_default_title'] = (getattr(site, 'site_name', '') or DEFAULT_SEO_TITLE)
    context['seo_default_description'] = (getattr(site, 'tagline', '') or DEFAULT_SEO_DESCRIPTION)
    return context
