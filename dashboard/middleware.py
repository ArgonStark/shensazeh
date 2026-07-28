import ipaddress

from .models import SiteVisit


class VisitTrackingMiddleware:
    """Records a SiteVisit for each page view."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Skip static/media files and AJAX requests
        path = request.path
        if (
            path.startswith('/static/')
            or path.startswith('/media/')
            or path.startswith('/admin/')
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        ):
            return response

        # Only track successful page views. Never let tracking break a request
        # (e.g. read-only DB on serverless hosts).
        if response.status_code == 200:
            try:
                ip = self._get_client_ip(request)
                # Loopback means the box talking to itself — local `runserver`
                # browsing and server-side curl health checks — never a real
                # visitor, so it must not land in the traffic stats.
                if not self._is_loopback(ip):
                    SiteVisit.objects.create(
                        ip_address=ip,
                        path=path,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                        user=request.user if request.user.is_authenticated else None,
                    )
            except Exception:
                pass

        return response

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')

    @staticmethod
    def _is_loopback(ip):
        """True for 127.0.0.0/8 and ::1. Unparseable addresses are kept —
        dropping them would silently lose real traffic."""
        try:
            return ipaddress.ip_address(ip).is_loopback
        except ValueError:
            return False
