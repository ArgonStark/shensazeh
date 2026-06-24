# Sazandeh — Development Roadmap to Production

> A staged plan to take **Sazandeh** (Persian construction tools & materials platform) from its current state to a stable, secure, live production deployment.
>
> Last updated: 2026-06-24

---

## 1. Executive Summary

**What exists today**

- Django 6.0.3 project, Python 3.14, SQLite (dev) with a MySQL switch (`DB_ENGINE`).
- Apps: `accounts` (mobile-OTP auth), `store`, `orders`, `inventory`, `blog`, `services`, `dashboard`, `telegram_bot`, `admin_panel`.
- Two admin surfaces: Django `/admin/` (developer) and a custom Persian/RTL `/panel/` (staff operations).
- Public storefront (Bootstrap 5 RTL) + custom staff panel (Tailwind, Alpine, Chart.js, Quill, Tom Select, SortableJS).
- Editable site content (`SiteSetting` singleton) surfaced via a `site` context processor.
- AI blog assist (Anthropic Claude Haiku), Telegram product notifications, WeasyPrint PDF invoices, Jalali dates throughout.

**What is missing / blocking go-live** (detailed in the phases below)

- No automated tests, no CI/CD, no production hardening.
- No customer-facing ordering/checkout or payment gateway (storefront is catalog-only).
- Integrations are dev-stubbed: SMS is console-only; Telegram sender is **broken** (async API called synchronously); AI requires an API key that may be unreachable from Iran.
- No production static/media serving, WSGI server, reverse proxy, HTTPS, logging, monitoring, or backups.
- Residual template/model "schema drift" in untouched apps needs an audit.

**Estimated effort:** ~6–9 focused weeks for a single developer to a solid v1 launch, depending on whether full e-commerce checkout is in scope (see Decision D2).

---

## 2. Guiding Principles

1. **Stabilize before extending** — fix known bugs and add a test safety net before building new features.
2. **Iran-first reality** — SMS, payments, and hosting must use providers that work inside Iran; some foreign APIs (e.g. Anthropic) are sanctioned/blocked and need a mitigation.
3. **Secrets in `.env`, never in code or DB.**
4. **Every phase ends green** — `python manage.py check --deploy` and the test suite pass before moving on.
5. **Ship the smallest correct thing** — a catalog + inquiry site can go live before full checkout if that unblocks the business.

---

## 3. Decisions Needed Up Front (blocking)

| # | Decision | Why it matters | Recommendation |
|---|----------|----------------|----------------|
| **D1** | **Currency unit** — prices are stored in **Rial** but the storefront shows the raw number labelled «تومان» (10× off). | Wrong prices shown to customers. | Pick one: keep Rial in DB and divide by 10 for display, or migrate values to Toman. Add a single `price_toman` template filter/property so it's consistent everywhere. |
| **D2** | **Is this a transactional store or a catalog/lead-gen site?** Today there is no cart/checkout; `Order`/`Invoice` are created by staff only. | Determines whether Phase 1 (checkout + payment) is needed for launch. | For a construction-materials B2B/B2C, a **catalog + "request quote"/phone-order** launch is often enough for v1; add checkout in v2. |
| **D3** | **Payment gateway** (if D2 = transactional). | Iranian gateways only. | **Zarinpal** (simplest) or IDPay/NextPay; Shaparak-backed. |
| **D4** | **SMS provider** for OTP + notifications. | OTP login is unusable in prod with the console provider. | **Kavenegar** or **SMS.ir** / Melipayamak. Implement behind the existing `SMSProvider` interface. |
| **D5** | **AI assist in production** — Anthropic API is generally **not reachable from Iran**. | Blog AI feature will fail in prod. | Either route via a server outside Iran / proxy, make the feature optional/disable-able, or swing to a locally reachable LLM. Keep it behind a feature flag. |
| **D6** | **Hosting & DB** — Iranian cloud (ArvanCloud, etc.) vs. VPS. | Affects deploy strategy, latency, payment to provider. | Iranian VPS/cloud + managed MySQL or self-hosted MySQL/Postgres. |
| **D7** | **Database engine** for prod — MySQL (already wired) vs Postgres. | Migrations/feature parity. | Stick with **MySQL** (already supported via PyMySQL) unless there's a reason to switch. |

---

## Phase 0 — Stabilization & Audit (foundation)

**Goal:** trustworthy codebase with a safety net. No new features.

- [ ] **Initialize git** (repo currently not under version control). Add a sensible `.gitignore` (already present) and make the first commit; set up a remote.
- [ ] **Full template ↔ model/view audit.** Storefront home/category/product and the admin dashboard were already corrected, but the same "imagined schema" drift likely remains in untouched templates:
  - [ ] `services/` templates (`service_list/detail`, `project_list/detail`) vs `Service`/`Project` fields.
  - [ ] `blog/` templates (`blog_list/detail`, `announcement_list`) vs `BlogPost`/`Announcement` (note `views_count`, `excerpt`, `author`).
  - [ ] `accounts/` templates (`login`, `verify_otp`, `profile`, `complete_profile`, `staff_list`).
  - [ ] `orders/` templates (`order_list/detail`, `invoice_*`).
  - [ ] Remaining `admin_panel/` list/form templates not yet exercised.
  - **Method:** render every URL with the test client (authenticated + anonymous) and assert HTTP 200; grep templates for attributes not on the model.
- [ ] **Fix known bugs (see §14 register):** Telegram async bug, visit-tracking write cost, currency display, `ProductReviewCreateView` invalid-form template, pagination `querystring` variable.
- [ ] **Consolidate the duplicated `StaffRequiredMixin`** (one in `accounts/views.py`, one in `admin_panel/views.py`) into a single shared mixin.
- [ ] **Add a smoke-test command/script** that hits all primary routes; wire it into CI later.
- [ ] **Pin & audit dependencies** (`pip list --outdated`, security advisories). Add `gunicorn`/`uvicorn`, `whitenoise`, `mysqlclient` (or keep PyMySQL), `sentry-sdk`, `django-environ`/keep `python-decouple`.

---

## Phase 1 — Core Commerce Features (only if D2 = transactional)

**Goal:** a customer can find, order, and pay for products.

- [ ] **Cart** — session-based cart (anonymous) that merges into the user on login.
- [ ] **Checkout flow** — address selection (reuse `User` address fields), shipping method, order summary → creates an `Order` + `OrderItem` from the cart (reuse `Order.recalculate_total()`).
- [ ] **Stock enforcement** — decrement stock via `InventoryEntry` (out) on order confirmation; prevent overselling; handle race conditions in a transaction.
- [ ] **Payment integration** (D3) — redirect to gateway, verify callback, mark `Order`/`Invoice` paid, handle failure/timeout, idempotent verification.
- [ ] **Order lifecycle** — surface the existing `STATUS_CHOICES` to customers (pending→…→delivered) with a "my orders" page and status updates from `/panel/`.
- [ ] **Invoice on paid order** — auto-generate the `Invoice` from the `Order` (the staff invoice flow already exists; reuse it).
- [ ] **Email/SMS order confirmations** (depends on D4).

> If D2 = catalog/lead-gen: replace this phase with a **"Request a quote / call to order"** flow (a simple inquiry form → stored model + Telegram/SMS notification to staff). Much smaller; can launch first.

---

## Phase 2 — Content, Admin Completeness & SEO

**Goal:** staff control everything customers see; search engines can find it.

- [ ] **Homepage management** — extend `SiteSetting` (or a new model) so staff edit the hero image/title/subtitle, feature tiles, and CTA from `/panel/` (today these are hardcoded in `home.html`).
- [ ] **Product search on the storefront** — wire the existing `ProductSearchAPIView` + navbar live-search dropdown (the JS hook `#searchResults` exists; finish it). Consider DB full-text or a search lib later.
- [ ] **Category/product filtering & sorting** on listing pages (price range, in-stock, sort) — the old template had UI stubs; back them with real querysets.
- [ ] **Reviews moderation** UX in `/panel/` (approve/reject already exists — verify the flow end-to-end).
- [ ] **SEO essentials:**
  - [ ] Per-page `<title>`/meta description, Open Graph/Twitter cards (especially product & blog).
  - [ ] `sitemap.xml` (Django `sitemaps` framework) + `robots.txt`.
  - [ ] Canonical URLs, structured data (Product/Breadcrumb JSON-LD).
  - [ ] Persian-friendly slugs already supported (`allow_unicode`).
- [ ] **Custom error pages** — branded `404.html` / `500.html` / `403.html`.
- [ ] **Image handling** — validate uploads, generate thumbnails (e.g. `easy-thumbnails`/`sorl-thumbnail`), enforce size/format; lazy-load already in place.
- [ ] **Accessibility pass** — labels, alt text, focus states, contrast (see `ui-ux-design` skill checklist).

---

## Phase 3 — Integrations (make the stubs real)

- [ ] **SMS provider (D4)** — implement a real `SMSProvider` (Kavenegar/SMS.ir) behind the existing abstract interface in `accounts/sms_service.py`; pick provider via env; keep `ConsoleSMSProvider` for dev. Add rate-limiting on OTP requests (anti-abuse) and OTP attempt throttling.
- [ ] **Telegram (fix + finish)** — `telegram_bot/service.py` calls `bot.send_message()` synchronously, but python-telegram-bot 22.x is **async-only**, so notifications currently never send. Fix by either using `asyncio.run(...)`, or (simpler/robust) calling the Telegram Bot HTTP API directly with `httpx` (already a dependency). Make it fully non-fatal and retry-safe.
- [ ] **AI assist (D5)** — gate behind a feature flag + graceful degradation when the key/endpoint is unavailable; surface clear errors in `/panel/`. Confirm model id via the `claude-api` skill before shipping.
- [ ] **Outbound email** (optional) — configure SMTP for order/admin notifications if used.

---

## Phase 4 — Security Hardening

**Goal:** pass `manage.py check --deploy` with no warnings.

- [ ] **Settings split** — `base/dev/prod` settings (or env-driven). `DEBUG=False` in prod; real `SECRET_KEY`; explicit `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`.
- [ ] **HTTPS & cookies** — `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_PROXY_SSL_HEADER` (behind nginx), `X_FRAME_OPTIONS`.
- [ ] **Auth/OTP abuse controls** — throttle OTP send/verify per mobile + IP; lock after N failures; expire codes (already 2 min).
- [ ] **Lock down `/admin/`** — superuser-only, optionally move off the default path / IP-allowlist; staff use `/panel/` only.
- [ ] **Permissions audit** — confirm every `/panel/` view is behind the staff mixin; consider per-role permissions (the `StaffProfile.ROLE_CHOICES` exist but aren't enforced — e.g. warehouse vs accountant access).
- [ ] **Input/file-upload validation**, size limits, content-type checks; `DATA_UPLOAD_MAX_*` tuned.
- [ ] **Dependency & secret scanning**; rotate any secrets that ever touched git history.
- [ ] **Rate limiting / WAF** at the proxy layer; basic bot filtering for the visit tracker.

---

## Phase 5 — Testing & QA

**Goal:** confidence to deploy and refactor.

- [ ] **Unit tests** — models (Order totals, Invoice/Order number generation, `InventoryEntry` stock side-effect, `SiteSetting` singleton, `Product.is_available/image_url`), forms, OTP expiry logic.
- [ ] **View/integration tests** — auth flow (OTP), storefront pages, `/panel/` CRUD, checkout/payment callback (mock gateway), permissions (anon/staff/superuser).
- [ ] **Template smoke tests** — assert 200 for every route (catches schema drift permanently).
- [ ] **Manual QA matrix** — RTL rendering, mobile breakpoints, Jalali dates, Persian number formatting, PDF invoice output, Quill RTL editor.
- [ ] **Coverage target** ≥ 70% on core apps; fail CI below threshold.
- [ ] **Load sanity** — basic load test on listing/search; check N+1 queries (`django-debug-toolbar`/`nplusone` in dev).

---

## Phase 6 — Production Infrastructure & Deployment

**Goal:** reproducible, observable production environment.

- [ ] **App server** — `gunicorn` (sync) or `uvicorn`+`gunicorn` (if async needed for Telegram). Configure workers/timeouts.
- [ ] **Reverse proxy** — nginx terminating TLS, serving `/static/` and `/media/`, gzip/brotli, security headers, client max body size.
- [ ] **Static files** — `collectstatic` + **WhiteNoise** (or nginx) with hashed filenames (`ManifestStaticFilesStorage`) → replaces the manual `?v=` cache-busting.
- [ ] **Media storage** — persistent volume or object storage (ArvanCloud S3-compatible); never served by Django in prod.
- [ ] **Database** — provisioned MySQL (utf8mb4), least-privilege user, connection pooling, `migrate` on deploy, seed the `SiteSetting`/superuser.
- [ ] **Environment config** — `.env` on server (not in repo); document every key (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_*`, `TELEGRAM_*`, `SMS_*`, `ANTHROPIC_API_KEY`, payment keys, `SITE_URL`).
- [ ] **Containerization (recommended)** — `Dockerfile` + `docker-compose` (web, db, nginx) for parity; or document a venv+systemd setup.
- [ ] **CI/CD** — pipeline: install → lint → test → build → deploy; block on red. Tag releases.
- [ ] **Zero-downtime-ish deploy** — migrate, collectstatic, restart workers; rollback plan.
- [ ] **TLS certs** — Let's Encrypt auto-renew (or Iranian CA if required).
- [ ] **Time zone/locale** — confirm server `Asia/Tehran`, `USE_TZ=True` handling for Jalali display.

---

## Phase 7 — Observability & Operations

- [ ] **Logging** — structured logging config (app + gunicorn + nginx); log levels per env; no secrets in logs.
- [ ] **Error tracking** — Sentry (or self-hosted GlitchTip) for exceptions.
- [ ] **Uptime & health** — `/healthz` endpoint, external uptime monitor, alerting (Telegram/email).
- [ ] **Metrics** — request rate/latency/error dashboards; DB slow-query log.
- [ ] **Backups** — automated DB dumps + media backups, off-site, with a **tested restore** procedure and retention policy.
- [ ] **Visit tracking at scale** — current middleware writes one row per pageview synchronously; move to async/batched writes or an analytics tool, and prune/aggregate old `SiteVisit` rows.

---

## Phase 8 — Launch (Go-Live Checklist)

- [ ] D1–D7 decisions resolved and implemented.
- [ ] `python manage.py check --deploy` clean; `DEBUG=False`.
- [ ] All tests green in CI; coverage threshold met.
- [ ] Real `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` set.
- [ ] HTTPS enforced; security headers verified (e.g. securityheaders.com / Mozilla Observatory).
- [ ] Static & media served correctly; favicon, logo, OG images present.
- [ ] OTP SMS works against the real provider; rate limiting on.
- [ ] Payment end-to-end tested with a real (small) transaction + refund path (if transactional).
- [ ] Telegram notifications verified; AI assist flagged on/off per D5.
- [ ] SEO: sitemap/robots reachable, meta/OG correct, Search Console verified.
- [ ] Custom 404/500 pages live.
- [ ] Backups running + restore rehearsed.
- [ ] Error tracking + uptime alerts active.
- [ ] Superuser created; staff accounts + roles set; default temp passwords rotated.
- [ ] Legal: privacy/terms pages, eNamad (نماد اعتماد) & Samandehi registration for an Iranian e-commerce site, business contact info accurate.
- [ ] DNS cutover plan + rollback; announce maintenance window.

---

## Phase 9 — Post-Launch

- [ ] Monitor errors/performance daily for the first weeks; triage and hotfix.
- [ ] Analytics review (traffic, conversion, search terms) → backlog.
- [ ] Iterate: wishlist, discount codes/campaigns, related-products tuning, blog content cadence, advanced search/filtering.
- [ ] Per-role staff permissions (enforce `StaffProfile` roles).
- [ ] Performance: caching (per-view/fragment), CDN for media, query optimization.
- [ ] Scheduled jobs (e.g. Celery/`django-cron`) for digests, stock alerts, abandoned-cart, `SiteVisit` aggregation.
- [ ] Regular dependency updates & security patching cadence.

---

## 14. Known Bugs / Tech-Debt Register

| ID | Severity | Item | Location | Notes |
|----|----------|------|----------|-------|
| B1 | High | Telegram sender never sends — async API called synchronously | `telegram_bot/service.py` | PTB 22.x is async-only; use `httpx` to the Bot HTTP API or `asyncio.run`. |
| B2 | High | Currency unit mismatch (Rial stored, «تومان» shown) | storefront templates | Decision D1; centralize a display filter. |
| B3 | Med | Residual template/model schema drift in untouched apps | `services/`, `blog/`, `accounts/`, `orders/` templates | Phase 0 audit via test-client 200 checks. |
| B4 | Med | Visit tracking does a synchronous DB write per pageview | `dashboard/middleware.py` | Bloats DB, adds latency; batch/async + bot filtering. |
| B5 | Med | `StaffRequiredMixin` duplicated | `accounts/views.py`, `admin_panel/views.py` | Consolidate. |
| B6 | Low | `ProductReviewCreateView` renders `store/review_form.html` on invalid form (may not exist) | `store/views.py` | Add template or redirect-with-message. |
| B7 | Low | `_pagination.html` uses a `querystring` var not provided by views | `templates/partials/_pagination.html` | Add a context/`querystring` tag so filters survive paging. |
| B8 | Low | Manual CSS cache-busting (`?v=...`) | `templates/base.html` | Replace with hashed static files in prod. |
| B9 | Low | `StaffProfile` roles defined but not enforced | panel views | Add per-role permission checks (Phase 4/9). |
| B10 | Info | No tests, no CI, not under git | repo-wide | Phases 0/5/6. |

---

## 15. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Anthropic API blocked from Iran** | AI blog assist fails in prod | D5: feature-flag + proxy/outside-Iran egress or disable. |
| **Payment/SMS provider onboarding** (KYC, business docs) can take time | Delays launch | Start provider registration early (parallel to dev). |
| **eNamad/Samandehi** required for Iranian e-commerce | Legal/trust blocker | Begin registration during Phase 2. |
| **Sanctioned dependencies/CDNs** (jsDelivr, fonts, Unsplash) may be unreliable from Iran | Broken UI/assets | Self-host critical CSS/JS/fonts and key images; avoid runtime dependence on foreign CDNs for prod. |
| **Data loss** | Severe | Phase 7 backups + tested restore before launch. |
| **Overselling / stock races** | Customer/ops pain | Transactional stock decrement in checkout (Phase 1). |
| **Scope creep on checkout** | Slips timeline | Consider catalog/lead-gen v1 (D2). |

---

## 16. Suggested Sequence & Rough Timeline (single dev)

| Weeks | Focus |
|-------|-------|
| 1 | Phase 0 (audit, bug fixes, git/CI skeleton) + resolve D1–D7 |
| 2–3 | Phase 3 integrations (SMS, Telegram fix) + Phase 2 SEO/content; **catalog/lead-gen launch path** if D2 says so |
| 3–5 | Phase 1 checkout + payment (if transactional) |
| 5–6 | Phase 4 security + Phase 5 testing |
| 6–7 | Phase 6 infra + deploy to staging |
| 7–8 | Phase 7 observability/backups + Phase 8 go-live checklist |
| 8+ | Launch + Phase 9 |

> Self-host foreign CDN assets (Bootstrap, Tailwind, Vazirmatn, Alpine, Quill, Swiper, AOS, Chart.js) and key images **before** launch to avoid in-country reachability issues — this also removes the runtime CDN dependency that affects every page.

---

*This roadmap is a living document. Update the checklists and registers as work lands. Pair it with the project memory and the `ui-ux-design` / `admin-crud` / `django-feature` skills under `.claude/skills/`.*
