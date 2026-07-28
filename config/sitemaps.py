"""XML sitemaps — how search engines discover published content.

`lastmod` is deliberately converted back to a Gregorian datetime: the models use
jDateTimeField, so the stored values are jdatetime objects, and the sitemap
framework formats lastmod as a W3C timestamp that must be Gregorian.
"""

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from blog.models import BlogPost
from services.models import Project, Service
from store.models import Category, Product


# Match the scheme the canonical tags advertise; the CDN terminates TLS and
# does not forward X-Forwarded-Proto, so the request would report "http".
PROTOCOL = 'https' if settings.SITE_URL.startswith('https') else None


def _gregorian(value):
    """jdatetime -> datetime, so W3C date formatting produces a valid date."""
    if value is None:
        return None
    togregorian = getattr(value, 'togregorian', None)
    return togregorian() if togregorian else value


class StaticViewSitemap(Sitemap):
    protocol = PROTOCOL
    priority = 0.7
    changefreq = 'weekly'

    def items(self):
        return ['home', 'store:category_list', 'services:service_list',
                'services:project_list', 'blog:blog_list', 'blog:announcement_list']

    def location(self, item):
        return reverse(item)


class BlogPostSitemap(Sitemap):
    protocol = PROTOCOL
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        return BlogPost.objects.filter(is_published=True)

    def lastmod(self, obj):
        return _gregorian(obj.updated_at)


class ProductSitemap(Sitemap):
    protocol = PROTOCOL
    priority = 0.7
    changefreq = 'daily'

    def items(self):
        return Product.objects.filter(is_active=True)


class CategorySitemap(Sitemap):
    protocol = PROTOCOL
    priority = 0.6
    changefreq = 'weekly'

    def items(self):
        return Category.objects.filter(is_active=True)


class ServiceSitemap(Sitemap):
    protocol = PROTOCOL
    priority = 0.7
    changefreq = 'monthly'

    def items(self):
        return Service.objects.filter(is_active=True)


class ProjectSitemap(Sitemap):
    protocol = PROTOCOL
    priority = 0.6
    changefreq = 'monthly'

    def items(self):
        return Project.objects.filter(is_active=True)

    def lastmod(self, obj):
        return _gregorian(obj.created_at)


SITEMAPS = {
    'static': StaticViewSitemap,
    'blog': BlogPostSitemap,
    'products': ProductSitemap,
    'categories': CategorySitemap,
    'services': ServiceSitemap,
    'projects': ProjectSitemap,
}
