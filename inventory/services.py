"""Server-authoritative stock movements.

Every stock change goes through record_movement() — never mutate
Product.stock directly and never create InventoryEntry rows by hand.
"""

from django.db import transaction

from finance.audit import log_action
from store.models import Product

from .models import InventoryEntry


class StockError(ValueError):
    """Invalid stock operation (oversell, bad quantity, …)."""


@transaction.atomic
def record_movement(product, entry_type, quantity, *, user=None, supplier='',
                    reference='', notes='', unit_cost=None, source=None,
                    order=None, allow_negative=False):
    """Append one kardex row and update the cached Product.stock atomically.

    - Locks the product row (select_for_update) against concurrent movements.
    - Outbound moves larger than current stock raise StockError unless
      allow_negative (which still floors the cache at zero, like legacy data).
    - An inbound 'in' with a unit_cost also refreshes the product's
      last-purchase price tier.
    """
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise StockError('تعداد نامعتبر است.')
    if quantity <= 0:
        raise StockError('تعداد باید بزرگ‌تر از صفر باشد.')
    if entry_type not in dict(InventoryEntry.ENTRY_TYPE_CHOICES):
        raise StockError('نوع حرکت انبار نامعتبر است.')

    product = Product.objects.select_for_update().get(pk=product.pk)
    inbound = entry_type in InventoryEntry.INBOUND_TYPES

    if inbound:
        new_stock = product.stock + quantity
    else:
        if quantity > product.stock and not allow_negative:
            raise StockError(
                f'موجودی «{product.name}» کافی نیست (موجودی: {product.stock}، درخواست: {quantity}).')
        new_stock = max(0, product.stock - quantity)

    entry = InventoryEntry(
        product=product,
        entry_type=entry_type,
        quantity=quantity,
        unit_cost=int(unit_cost) if unit_cost else 0,
        balance_after=new_stock,
        supplier=supplier,
        reference=reference,
        notes=notes,
        order=order,
        created_by=user,
    )
    if source is not None:
        entry.source = source
    entry.save()

    update_fields = ['stock']
    product.stock = new_stock
    if entry_type == 'in' and unit_cost:
        product.purchase_price = int(unit_cost)
        update_fields.append('purchase_price')
    product.save(update_fields=update_fields)

    log_action(user, 'create', entry)
    return entry
