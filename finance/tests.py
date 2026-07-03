from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from accounts.models import User

from . import audit, money, words
from .models import AuditLog
from .templatetags import finance_tags


class MoneyTests(TestCase):
    def test_rial_to_toman_truncates(self):
        self.assertEqual(money.rial_to_toman(1500000), 150000)
        self.assertEqual(money.rial_to_toman(19), 1)
        self.assertEqual(money.rial_to_toman(9), 0)
        self.assertEqual(money.rial_to_toman(0), 0)

    def test_rial_to_toman_negative_truncates_toward_zero(self):
        self.assertEqual(money.rial_to_toman(-19), -1)
        self.assertEqual(money.rial_to_toman(-9), 0)

    def test_toman_to_rial(self):
        self.assertEqual(money.toman_to_rial(150000), 1500000)

    def test_format_amount(self):
        self.assertEqual(money.format_amount(1500000), '1,500,000')
        self.assertEqual(money.format_amount(0), '0')
        self.assertEqual(money.format_amount(-42000), '-42,000')


class WordsTests(TestCase):
    def test_rial_words(self):
        self.assertEqual(words.rial_to_words(1500000), 'یک میلیون و پانصد هزار ریال')

    def test_zero(self):
        self.assertEqual(words.rial_to_words(0), 'صفر ریال')

    def test_negative(self):
        self.assertTrue(words.rial_to_words(-1000).startswith('منفی '))

    def test_toman_words_converts_unit(self):
        self.assertEqual(words.rial_to_toman_words(1500000), 'یکصد و پنجاه هزار تومان')


class FilterTests(TestCase):
    def test_toman_filter(self):
        self.assertEqual(finance_tags.toman(1500000), '150,000')

    def test_toman_filter_bad_value_passthrough(self):
        self.assertEqual(finance_tags.toman('n/a'), 'n/a')
        self.assertIsNone(finance_tags.toman(None))

    def test_rial_filter(self):
        self.assertEqual(finance_tags.rial(1500000), '1,500,000')

    def test_fa_digits(self):
        self.assertEqual(finance_tags.fa_digits('123'), '۱۲۳')
        self.assertEqual(finance_tags.fa_digits(45), '۴۵')


class AuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u1', mobile='09120000001', password='x')

    def test_create_logged_with_snapshot(self):
        log = audit.log_action(self.user, 'create', self.user)
        self.assertEqual(log.actor, self.user)
        self.assertEqual(log.action, 'create')
        self.assertEqual(log.object_id, self.user.pk)
        self.assertEqual(log.changes['after']['mobile'], '09120000001')

    def test_update_logs_only_diff(self):
        before = audit.model_snapshot(self.user)
        self.user.city = 'شیراز'
        self.user.save()
        after = audit.model_snapshot(self.user)
        log = audit.log_action(self.user, 'update', self.user, before=before, after=after)
        self.assertEqual(log.changes['city'], {'before': '', 'after': 'شیراز'})
        self.assertNotIn('mobile', log.changes)

    def test_delete_keeps_before_snapshot(self):
        before = audit.model_snapshot(self.user)
        log = audit.log_action(self.user, 'delete', self.user, before=before)
        self.assertEqual(log.changes['before']['mobile'], '09120000001')

    def test_anonymous_actor_stored_as_null(self):
        from django.contrib.auth.models import AnonymousUser
        log = audit.log_action(AnonymousUser(), 'create', self.user)
        self.assertIsNone(log.actor)

    def test_content_type_points_at_model(self):
        log = audit.log_action(self.user, 'create', self.user)
        self.assertEqual(log.content_type, ContentType.objects.get_for_model(User))
        self.assertEqual(AuditLog.objects.count(), 1)
