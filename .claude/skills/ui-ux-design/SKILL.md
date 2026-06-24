---
name: ui-ux-design
description: Apply this project's UI/UX standards when creating or reviewing any template (HTML). Covers Persian RTL layout, Vazirmatn typography, the Tailwind admin panel design system, the Bootstrap 5 storefront, accessibility, and responsive/mobile behavior. Use when adding pages, building components, or reviewing visual/interaction quality.
---

# UI/UX Design Standards — Sazandeh

This is a **Persian (Farsi), right-to-left** business app. Every screen must read naturally to a Persian user. There are **two distinct design systems** — never mix them.

## Which system am I in?

| Surface | Files | Stack |
|---|---|---|
| **Storefront** (public) | `templates/base.html`, `templates/partials/*`, `store/`, `blog/`, `services/` templates | Bootstrap 5 RTL + Bootstrap Icons + Swiper + AOS |
| **Admin panel** (staff) | `templates/admin_panel/**` | Tailwind (CDN) + Alpine.js + Chart.js + Tom Select + Quill + SortableJS |

Extend the right base: storefront pages `{% extends 'base.html' %}`, admin pages `{% extends 'admin_panel/base.html' %}`.

## Non-negotiable rules

1. **RTL first.** `dir="rtl"` is set on `<html>`. Use logical spacing that respects RTL. In Tailwind prefer `mr-*`/`ms-*` for the "start" side as the existing code does (e.g. main content uses `lg:mr-64` for the sidebar). Numeric/latin inputs (mobile, price, slug) get `dir="ltr"`.
2. **All user-facing text in Persian.** Labels, buttons, placeholders, empty states, errors, toasts — Farsi. Keep code identifiers/slugs in English.
3. **Vazirmatn font** is the only font. It's already loaded in both bases — don't add others.
4. **Persian digits for display.** Format numbers/currency with `.toLocaleString('fa-IR')` in JS, and `{% load humanize %}` + `intcomma` server-side. Currency unit is تومان in the UI.
5. **Jalali dates.** Models already use `jDateTimeField`; render dates as-is (they come out Shamsi). Never show Gregorian dates to users.

## Admin panel design system (Tailwind)

Match the existing visual language exactly — consistency over novelty:

- **Cards:** `bg-white rounded-xl shadow-sm border border-gray-200 p-6`
- **Primary button:** `px-6 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition`
- **Secondary button:** `px-4 py-2.5 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition`
- **Destructive:** red-600 family; always behind a confirm (`components/modal.html`).
- **Inputs:** `w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm`. Always pair with a `<label class="block text-sm font-medium text-gray-700 mb-1">`.
- **Field labels** blue accent on focus; **errors** in `bg-red-50 border border-red-200 rounded-xl` blocks (see `blog/post_form.html`).
- **Page header block:** breadcrumb (with the rotated chevron SVG) + `<h1 class="text-2xl font-bold text-gray-800">`. Reuse the `{% block page_header %}` pattern.
- **Feedback:** use Django `messages` → they auto-render as toasts via `components/toast.html`. Don't invent ad-hoc alerts; avoid raw `alert()` except for trivial client-side validation.
- **Icons:** inline Heroicons-style `<svg>` (stroke, `viewBox="0 0 24 24"`), matching existing markup. Don't pull a new icon library.
- **Reusable components** live in `templates/admin_panel/components/` — `stat_card`, `pagination`, `modal`, `toast`, `navbar`, `sidebar`. Prefer `{% include %}` over re-implementing.

### When to reach for the new libraries
- **Tom Select** → any select with many options (product/category pickers). Especially the invoice line-item product `<select>`.
- **Quill** → long rich-text fields (blog content). Sync to a hidden textarea on submit (see `post_form.html`).
- **SortableJS** → reorderable lists where a model has an `order` field (categories, services, product images).
- **Chart.js** → dashboard analytics only; feed it `json.dumps(...)` from the view like `AdminDashboardView` does.

## Storefront design system (Bootstrap 5 RTL)

- Use Bootstrap RTL utilities and components; Bootstrap Icons for iconography.
- **Swiper** for product/hero carousels; **AOS** (`data-aos="fade-up"`) for tasteful scroll reveals — already initialized in `base.html`.
- Cards, grids, and spacing via Bootstrap classes; keep custom CSS in `static/css/style.css`.

## Accessibility & responsive (both systems)

- Every input has an associated `<label for>`; icon-only buttons get `aria-label`.
- Maintain visible focus states (the input pattern above already does).
- Color contrast: body text `text-gray-800` on light bg — keep AA.
- Mobile: admin sidebar collapses via the Alpine `sidebarOpen` overlay pattern; storefront relies on Bootstrap's responsive grid. Test at `sm`/`lg` breakpoints. Tables should sit in `overflow-x-auto` wrappers (see invoice form).
- Always provide a Persian **empty state** for lists (e.g. "موردی یافت نشد").

## Review checklist (use when asked to review a template)

- [ ] Extends the correct base for its surface
- [ ] RTL correct; latin/numeric inputs `dir="ltr"`
- [ ] All visible strings in Persian, including empty/error states
- [ ] Numbers/dates formatted (fa-IR / humanize / Jalali)
- [ ] Matches the card/button/input class conventions above
- [ ] Reuses existing components instead of duplicating
- [ ] Labels + aria on controls; focus states intact
- [ ] Responsive: works on mobile, tables scroll, sidebar behaves
- [ ] Feedback via Django messages/toasts, confirm dialogs for destructive actions
