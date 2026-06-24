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

        # Only track successful page views
        if response.status_code == 200:
            ip = self._get_client_ip(request)
            SiteVisit.objects.create(
                ip_address=ip,
                path=path,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                user=request.user if request.user.is_authenticated else None,
            )

        return response

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')
