from .models import SiteSetting


def site_settings(request):
    """Expose the singleton SiteSetting to all templates as `site`."""
    try:
        return {'site': SiteSetting.load()}
    except Exception:
        # During initial migration the table may not exist yet.
        return {'site': None}
