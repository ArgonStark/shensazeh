from django.db import migrations


def backfill(apps, schema_editor):
    """Compute balance_after for historical movements per product, replaying
    the legacy clamp-at-zero behaviour, oldest first."""
    InventoryEntry = apps.get_model('inventory', 'InventoryEntry')
    Product = apps.get_model('store', 'Product')

    for product in Product.objects.all():
        balance = 0
        entries = (InventoryEntry.objects.filter(product=product)
                   .order_by('created_at', 'id'))
        for entry in entries:
            if entry.entry_type in ('in', 'return_in'):
                balance += entry.quantity
            else:
                balance = max(0, balance - entry.quantity)
            # queryset.update bypasses the model's immutability guard on save()
            InventoryEntry.objects.filter(pk=entry.pk).update(balance_after=balance)


def backfill_codes(apps, schema_editor):
    Product = apps.get_model('store', 'Product')
    for product in Product.objects.filter(code__isnull=True):
        Product.objects.filter(pk=product.pk).update(code=f'P{product.pk:05d}')


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_alter_inventoryentry_options_and_more'),
        ('store', '0002_product_code_product_expiry_date_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunPython(backfill_codes, migrations.RunPython.noop),
    ]
