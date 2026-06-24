---
name: django-feature
description: Add a Django model, field, or app-level feature to this project following its conventions (custom User, Jalali date fields, Persian verbose names, migrations, telegram/inventory side effects). Use when adding or changing models, writing migrations, wiring storefront views/URLs, or touching auth, orders, inventory, or telegram logic.
---

# Django Feature Development — Sazandeh

Conventions for backend work. The app is Django 6, Persian/RTL, SQLite in dev / MySQL in prod (switched by `DB_ENGINE` env var). Always work inside the venv: `source venv/bin/activate`.

## Model conventions (match existing models exactly)
- **Verbose names in Persian** for every field and the `Meta` (`verbose_name`, `verbose_name_plural`). See `store/models.py`.
- **Dates use Jalali fields**: `from django_jalali.db import models as jmodels` then `jmodels.jDateTimeField('تاریخ ایجاد', auto_now_add=True)`. Do NOT use plain `DateTimeField` for user-facing dates (the one exception is `OTPCode.created_at`, used only for expiry math).
- **Money** is stored as integer Rial: `PositiveBigIntegerField('قیمت (ریال)')`. UI displays تومان.
- **Slugs**: `SlugField(unique=True, allow_unicode=True)` so Persian slugs work.
- **FKs to the user model**: reference `'accounts.User'` (custom user, `AUTH_USER_MODEL`). Login identifier is `mobile`, not username.
- **`Meta.ordering`** is set on nearly every model — include it.
- Add an `__str__` returning something Persian-readable.

## Known side-effect patterns (don't break these)
- **Inventory adjusts stock**: `InventoryEntry.save()` increments/decrements `Product.stock` on create. New stock movements should go through `InventoryEntry`, not direct `stock` writes.
- **Telegram notification**: creating an `in` inventory entry triggers `telegram_bot.service.send_product_notification(product)` (wrapped in try/except in `AdminInventoryCreateView`). Keep it non-fatal.
- **Order/Invoice numbers** auto-generate in `save()` via `uuid` — don't set them manually.
- **Order totals**: use `Order.recalculate_total()` / `final_amount` rather than recomputing inline.

## Auth notes
- OTP login flow: `accounts/views.py` (`LoginView` → `VerifyOTPView`), code valid 2 minutes, SMS via `accounts/sms_service.py`.
- Staff gating everywhere uses a `StaffRequiredMixin` (`is_superuser or is_staff`). There are two copies — one in `accounts/views.py`, one in `admin_panel/views.py`. Reuse, don't invent a third.

## Workflow for a model change
1. Edit/add the model with the conventions above.
2. `python manage.py makemigrations <app>` then `python manage.py migrate`.
3. Register in that app's `admin.py` if it should appear in Django `/admin/`.
4. If it needs staff management UI → use the **admin-crud** skill for the `/panel/` section.
5. If it has public-facing pages → add view + URL + template extending `templates/base.html` (Bootstrap), per the **ui-ux-design** skill.
6. Run `python manage.py check` and exercise the path.

## Settings / secrets
- Config comes from `.env` via `python-decouple` (`config(...)`). Never hardcode secrets. Reading `.env` is blocked — ask the user for values rather than printing the file.
- Relevant keys: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_*`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `SMS_API_KEY`, `SMS_SENDER`, `ANTHROPIC_API_KEY`, `SITE_URL`.

## AI features
- Claude is used for Persian blog generation in `AdminAIAssistView` (model `claude-haiku-4-5-20251001`). When extending AI features, reuse the `anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)` client pattern and keep prompts in Persian. Consult the project's `claude-api` skill for current model IDs/params before changing models.
