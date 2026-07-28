from django.test import TestCase

from dashboard.middleware import VisitTrackingMiddleware
from dashboard.models import SiteVisit


class VisitTrackingLoopbackTests(TestCase):
    """Loopback requests are the box talking to itself (local `runserver`
    browsing, server-side curl health checks) and must not be counted as
    visitors — they once made 127.0.0.1 the top entry in the traffic stats.
    """

    def test_loopback_ipv4_is_not_recorded(self):
        self.client.get('/', REMOTE_ADDR='127.0.0.1')
        self.assertFalse(SiteVisit.objects.filter(ip_address='127.0.0.1').exists())

    def test_loopback_ipv6_is_not_recorded(self):
        self.client.get('/', REMOTE_ADDR='::1')
        self.assertFalse(SiteVisit.objects.filter(ip_address='::1').exists())

    def test_whole_127_block_is_loopback(self):
        # 127.0.0.0/8 is loopback in full, not just 127.0.0.1.
        self.assertTrue(VisitTrackingMiddleware._is_loopback('127.0.0.1'))
        self.assertTrue(VisitTrackingMiddleware._is_loopback('127.1.2.3'))
        self.assertTrue(VisitTrackingMiddleware._is_loopback('::1'))

    def test_real_addresses_are_kept(self):
        for ip in ('85.11.167.109', '95.64.116.201', '10.0.0.5', '2001:db8::1'):
            self.assertFalse(VisitTrackingMiddleware._is_loopback(ip), ip)

    def test_unparseable_address_is_kept(self):
        """Never drop traffic just because the address didn't parse."""
        self.assertFalse(VisitTrackingMiddleware._is_loopback('not-an-ip'))
        self.assertFalse(VisitTrackingMiddleware._is_loopback(''))

    def test_real_visitor_is_still_recorded(self):
        """The guard must not suppress genuine traffic."""
        self.client.get('/', REMOTE_ADDR='85.11.167.109')
        self.assertTrue(SiteVisit.objects.filter(ip_address='85.11.167.109').exists())

    def test_forwarded_client_ip_wins_over_loopback_peer(self):
        """Behind nginx the peer is loopback but XFF carries the real client;
        the visit must be recorded under the real address."""
        self.client.get('/', REMOTE_ADDR='127.0.0.1',
                        HTTP_X_FORWARDED_FOR='85.11.167.109, 127.0.0.1')
        self.assertTrue(SiteVisit.objects.filter(ip_address='85.11.167.109').exists())
        self.assertFalse(SiteVisit.objects.filter(ip_address='127.0.0.1').exists())
