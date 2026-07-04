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


class CashFlowTests(TestCase):
    def setUp(self):
        from admin_panel.permissions import apply_role_defaults
        self.accountant = User.objects.create_user(username='cf', mobile='09120005000', password='x', is_staff=True)
        apply_role_defaults(self.accountant, 'accountant')
        self.client.force_login(self.accountant)

    def test_create_category_and_transaction(self):
        from django.urls import reverse
        self.client.post(reverse('admin_panel:expense_category_create'),
                         {'name': 'کرایه حمل', 'kind': 'expense'})
        from .models import CashTransaction, ExpenseCategory
        category = ExpenseCategory.objects.get(name='کرایه حمل')
        response = self.client.post(reverse('admin_panel:cashflow_create'), {
            'kind': 'expense', 'category': category.pk, 'amount': 3_500_000,
            'date': '۱۴۰۴/۰۴/۱۰', 'description': 'نیسان بار', 'reference': '',
        })
        self.assertEqual(response.status_code, 302)
        tx = CashTransaction.objects.get()
        self.assertEqual(tx.amount, 3_500_000)
        self.assertEqual(tx.date.year, 1404)
        self.assertEqual(tx.signed_amount, -3_500_000)

    def test_kind_category_mismatch_rejected(self):
        from django.urls import reverse

        from .models import CashTransaction, ExpenseCategory
        category = ExpenseCategory.objects.create(name='فروش ضایعات', kind='income')
        self.client.post(reverse('admin_panel:cashflow_create'), {
            'kind': 'expense', 'category': category.pk, 'amount': 100,
            'date': '1404/04/10', 'description': '', 'reference': '',
        })
        self.assertEqual(CashTransaction.objects.count(), 0)

    def test_cashflow_page_renders_summary(self):
        import jdatetime
        from django.urls import reverse

        from .models import CashTransaction, ExpenseCategory
        income_cat = ExpenseCategory.objects.create(name='درآمد اجاره', kind='income')
        CashTransaction.objects.create(kind='income', category=income_cat, amount=10_000_000,
                                       date=jdatetime.date.today())
        response = self.client.get(reverse('admin_panel:cashflow'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1,000,000')  # 10M Rial → 1M Toman

    def test_warehouse_cannot_see_cashflow(self):
        from admin_panel.permissions import apply_role_defaults
        from django.urls import reverse
        wh = User.objects.create_user(username='cfw', mobile='09120005001', password='x', is_staff=True)
        apply_role_defaults(wh, 'warehouse')
        self.client.force_login(wh)
        self.assertEqual(self.client.get(reverse('admin_panel:cashflow')).status_code, 403)


class BackupCommandTests(TestCase):
    def test_backup_and_rotation(self):
        import tempfile
        from pathlib import Path

        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp:
            call_command('backup_db', '--dir', tmp, '--keep', '2')
            call_command('backup_db', '--dir', tmp, '--keep', '2')
            call_command('backup_db', '--dir', tmp, '--keep', '2')
            backups = list(Path(tmp).glob('db-*'))
            self.assertEqual(len(backups), 2)  # rotated down to --keep
            self.assertTrue(all(b.stat().st_size > 0 for b in backups))


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
