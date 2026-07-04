# Sazandeh (شن‌سازه)

A Django-based business management system for a Persian tools & construction-materials
company. It combines a public storefront, a Telegram bot, and a full staff back-office
covering inventory, sales invoicing, parties/CRM, finance, cheques, and installment sales.

The UI is fully right-to-left (RTL) Persian, dates are Jalali (Shamsi), and money is
handled in Toman/Rial with amount-in-words support.

## Features

- **Storefront** — product catalog, search, blog, and service pages.
- **Staff panel** (`/panel/`) — custom admin panel with granular per-user permissions
  and an audit trail (separate from Django's built-in admin).
- **Inventory** — immutable stock ledger (kardex) with product management.
- **Orders & Invoicing** — typed financial documents with an atomic issue flow.
- **Parties** — customers/suppliers with immutable account ledgers.
- **Finance** — money utilities, Toman/words filters, expense & income register,
  monthly cash-flow, payment auto-settlement, and a Jalali financial calendar with
  reminders. Excel ledger export.
- **Cheques** — received/issued cheque lifecycle with printable layouts.
- **Installments** — installment sales with documented interest methods.
- **CRM** — campaigns and SMS gateway integration.
- **Telegram bot** — customer-facing bot integration.
- **Dashboard** — finance widgets and business overview.

## Tech stack

- **Python / Django 6.0**, Django REST Framework
- **Database:** SQLite by default; MySQL (via PyMySQL) in production
- **Jalali dates:** `django-jalali`, `jdatetime`
- **PDF/print:** WeasyPrint
- **Static files:** WhiteNoise
- **Deployment:** Gunicorn + nginx (see `deploy/`); Vercel demo config in `vercel.json`
- Localization: `fa`, timezone `Asia/Tehran`

## Getting started

```bash
# 1. Create and activate a virtualenv
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment (see below), then run migrations
python manage.py migrate

# 4. Create a superuser
python manage.py createsuperuser   # or: python create_superuser.py

# 5. Run the dev server
python manage.py runserver
```

### Environment

Settings are read from a `.env` file via `python-decouple`. Common variables:

| Variable | Default | Notes |
|----------|---------|-------|
| `SECRET_KEY` | — | Django secret key |
| `DEBUG` | — | `True` for local development |
| `DB_ENGINE` | `django.db.backends.sqlite3` | Use `django.db.backends.mysql` for MySQL |
| `DB_NAME` | `db.sqlite3` | DB name / path |
| `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | — | Required for MySQL |

Authentication is email + password (custom `accounts.User` model); mobile/OTP (SMS)
auth is planned.

## Project layout

```
config/         # settings, root URLs, wsgi/asgi
accounts/       # custom User, auth
store/          # storefront catalog
inventory/      # stock ledger (kardex)
orders/         # orders & invoicing documents
parties/        # customers & suppliers ledgers
finance/        # money utils, expenses/income, calendar, settlement
cheques/        # received/issued cheques
installments/   # installment sales
crm/            # campaigns & SMS
blog/           # blog
services/       # service pages
dashboard/      # staff dashboard
admin_panel/    # custom staff back-office
telegram_bot/   # Telegram integration
deploy/         # gunicorn/nginx deployment kit
```

## Key routes

- `/` — storefront home
- `/store/`, `/blog/`, `/services/` — public pages
- `/panel/` — staff back-office
- `/dashboard/` — dashboard
- `/admin/` — Django admin
- `/api/products/search/` — product search API

## Roadmap

See [ROADMAP.md](ROADMAP.md).
