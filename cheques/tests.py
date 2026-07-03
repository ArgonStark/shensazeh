import jdatetime
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from admin_panel.permissions import apply_role_defaults
from finance.models import AuditLog
from parties.models import LedgerEntry, Party

from .models import Cheque, ChequeBook, ChequePrintLayout
from .services import ChequeError, set_cheque_status


def make_cheque(party, direction='received', amount=5_000_000, days=10, **kwargs):
    import datetime
    return Cheque.objects.create(
        direction=direction, party=party, serial='123456', bank_name='ملت',
        amount=amount, due_date=jdatetime.date.today() + datetime.timedelta(days=days),
        **kwargs,
    )


class ChequeLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='acc', mobile='09120004000', password='x', is_staff=True)
        self.party = Party.objects.create(name='مشتری چکی')

    def test_received_cheque_clears_to_party_credit(self):
        cheque = make_cheque(self.party, 'received')
        self.assertEqual(self.party.balance, 0)  # pending cheque is not money
        set_cheque_status(cheque, 'cleared', self.user)
        entry = LedgerEntry.objects.get()
        self.assertEqual(entry.entry_type, LedgerEntry.CREDIT)
        self.assertEqual(entry.amount, 5_000_000)
        self.assertEqual(entry.source, cheque)
        self.assertEqual(self.party.balance, -5_000_000)

    def test_issued_cheque_clears_to_party_debit(self):
        cheque = make_cheque(self.party, 'issued')
        set_cheque_status(cheque, 'cleared', self.user)
        self.assertEqual(LedgerEntry.objects.get().entry_type, LedgerEntry.DEBIT)
        self.assertEqual(self.party.balance, 5_000_000)

    def test_bounced_posts_nothing(self):
        cheque = make_cheque(self.party)
        cheque = set_cheque_status(cheque, 'bounced', self.user)
        self.assertEqual(cheque.status, 'bounced')
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertTrue(AuditLog.objects.filter(action='status', object_id=cheque.pk).exists())

    def test_final_states_are_final(self):
        cheque = make_cheque(self.party)
        set_cheque_status(cheque, 'cleared', self.user)
        for target in ('pending', 'bounced', 'cleared'):
            with self.assertRaises(ChequeError):
                set_cheque_status(cheque, target, self.user)
        self.assertEqual(LedgerEntry.objects.count(), 1)  # no double posting

    def test_invalid_status_rejected(self):
        cheque = make_cheque(self.party)
        with self.assertRaises(ChequeError):
            set_cheque_status(cheque, 'eaten', self.user)

    def test_overdue_flag(self):
        overdue = make_cheque(self.party, days=-1)
        future = make_cheque(self.party, days=5)
        self.assertTrue(overdue.is_overdue)
        self.assertFalse(future.is_overdue)
        set_cheque_status(overdue, 'cleared', self.user)
        overdue.refresh_from_db()
        self.assertFalse(overdue.is_overdue)  # only pending cheques are overdue

    def test_amount_words(self):
        cheque = make_cheque(self.party, amount=1_500_000)
        self.assertEqual(cheque.amount_words, 'یک میلیون و پانصد هزار ریال')


class ChequePanelTests(TestCase):
    def setUp(self):
        self.accountant = User.objects.create_user(username='acc2', mobile='09120004001', password='x', is_staff=True)
        apply_role_defaults(self.accountant, 'accountant')
        self.seller = User.objects.create_user(username='sl', mobile='09120004002', password='x', is_staff=True)
        apply_role_defaults(self.seller, 'sales')
        self.party = Party.objects.create(name='طرف چک')

    def test_create_cheque_via_panel(self):
        self.client.force_login(self.accountant)
        response = self.client.post(reverse('admin_panel:cheque_create'), {
            'direction': 'received', 'party': self.party.pk, 'invoice': '', 'cheque_book': '',
            'serial': '998877', 'sayad_id': '', 'bank_name': 'صادرات', 'branch': '',
            'amount': 12_000_000, 'due_date': '۱۴۰۵/۰۲/۱۵', 'payee': '', 'description': '',
        })
        self.assertEqual(response.status_code, 302)
        cheque = Cheque.objects.get(serial='998877')
        self.assertEqual(cheque.due_date, jdatetime.date(1405, 2, 15))  # Persian digits parsed
        self.assertEqual(cheque.status, 'pending')

    def test_bad_date_rejected(self):
        self.client.force_login(self.accountant)
        response = self.client.post(reverse('admin_panel:cheque_create'), {
            'direction': 'received', 'party': self.party.pk, 'serial': '1', 'bank_name': 'ملی',
            'amount': 100, 'due_date': 'فردا', 'invoice': '', 'cheque_book': '', 'sayad_id': '',
            'payee': '', 'description': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Cheque.objects.count(), 0)

    def test_sales_can_add_but_not_clear(self):
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(reverse('admin_panel:cheque_create')).status_code, 200)
        cheque = make_cheque(self.party)
        response = self.client.post(reverse('admin_panel:cheque_status', args=[cheque.pk]),
                                    {'status': 'cleared'})
        self.assertEqual(response.status_code, 403)
        cheque.refresh_from_db()
        self.assertEqual(cheque.status, 'pending')

    def test_status_endpoint_clears(self):
        self.client.force_login(self.accountant)
        cheque = make_cheque(self.party)
        self.client.post(reverse('admin_panel:cheque_status', args=[cheque.pk]), {'status': 'cleared'})
        cheque.refresh_from_db()
        self.assertEqual(cheque.status, 'cleared')

    def test_cleared_cheque_not_editable(self):
        self.client.force_login(self.accountant)
        cheque = make_cheque(self.party)
        set_cheque_status(cheque, 'cleared', self.accountant)
        response = self.client.get(reverse('admin_panel:cheque_edit', args=[cheque.pk]))
        self.assertEqual(response.status_code, 302)  # bounced back to the list

    def test_due_report_renders(self):
        self.client.force_login(self.accountant)
        make_cheque(self.party, days=-2)
        make_cheque(self.party, days=7, direction='issued')
        response = self.client.get(reverse('admin_panel:cheque_due_report'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'چک‌های معوق')

    def test_print_page_creates_default_layout(self):
        self.client.force_login(self.accountant)
        cheque = make_cheque(self.party, direction='issued')
        response = self.client.get(reverse('admin_panel:cheque_print', args=[cheque.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ChequePrintLayout.objects.filter(bank_name='ملت').exists())
        self.assertContains(response, 'یک میلیون' if cheque.amount == 1_500_000 else 'میلیون')

    def test_chequebook_create_and_toggle(self):
        self.client.force_login(self.accountant)
        self.client.post(reverse('admin_panel:chequebook_create'), {
            'bank_name': 'تجارت', 'branch': 'مرکزی', 'account_number': '111',
            'serial_from': '100', 'serial_to': '150', 'notes': '', 'is_active': 'on',
        })
        book = ChequeBook.objects.get(bank_name='تجارت')
        self.client.post(reverse('admin_panel:chequebook_toggle', args=[book.pk]))
        book.refresh_from_db()
        self.assertFalse(book.is_active)
