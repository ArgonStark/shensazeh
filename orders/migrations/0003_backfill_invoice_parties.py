from django.db import migrations


def backfill(apps, schema_editor):
    """Convert legacy simple invoices into the new document model:

    - every existing invoice becomes an issued sale document (they were real,
      printed invoices — numbers are kept as-is)
    - a Party is created/matched from the denormalized customer text
    - the party ledger gets the historical debit (+ matching credit when the
      invoice was already marked paid) so balances start out correct
    """
    Invoice = apps.get_model('orders', 'Invoice')
    Party = apps.get_model('parties', 'Party')
    LedgerEntry = apps.get_model('parties', 'LedgerEntry')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    try:
        invoice_ct = ContentType.objects.get(app_label='orders', model='invoice')
    except ContentType.DoesNotExist:
        invoice_ct = None  # fresh DB mid-chain; there are no invoices either

    for invoice in Invoice.objects.all().order_by('created_at'):
        # 1) party from the customer snapshot
        party = None
        mobile = (invoice.customer_mobile or '').strip()
        if mobile and mobile != '0000000000':
            party = Party.objects.filter(mobile=mobile).first()
        if party is None and invoice.customer_name:
            party = Party.objects.filter(name=invoice.customer_name).first()
        if party is None:
            party = Party.objects.create(
                name=invoice.customer_name or 'مشتری متفرقه',
                mobile='' if mobile == '0000000000' else mobile,
                address=invoice.customer_address or '',
                party_type='customer',
            )

        # 2) status/type
        Invoice.objects.filter(pk=invoice.pk).update(
            party=party, doc_type='sale', status='issued',
            issued_at=invoice.created_at, vat_rate=0,
        )

        # 3) opening ledger rows (idempotent: skip if this doc already posted)
        if invoice_ct and not LedgerEntry.objects.filter(
                content_type=invoice_ct, object_id=invoice.pk).exists():
            if invoice.total > 0:
                LedgerEntry.objects.create(
                    party=party, entry_type='debit', amount=invoice.total,
                    description=f'فاکتور فروش {invoice.invoice_number} (سوابق)',
                    content_type=invoice_ct, object_id=invoice.pk,
                )
                if invoice.is_paid:
                    LedgerEntry.objects.create(
                        party=party, entry_type='credit', amount=invoice.total,
                        description=f'تسویه فاکتور {invoice.invoice_number} (سوابق)',
                        content_type=invoice_ct, object_id=invoice.pk,
                    )


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_numberseries_invoice_cancelled_at_and_more'),
        ('parties', '0001_initial'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
