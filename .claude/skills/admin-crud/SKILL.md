---
name: admin-crud
description: Scaffold a complete custom admin-panel CRUD section (list, create, edit, delete + URLs + Persian Tailwind templates) for a Django model, following this project's exact admin_panel conventions. Use when the user wants to manage a model in the /panel/ staff panel, add a new admin section, or wire an existing model into the admin panel.
---

# Admin Panel CRUD Scaffold — Sazandeh

Generates a full management section in the **custom** admin panel at `/panel/` (the app `admin_panel`). This is NOT Django's built-in `/admin/`. Follow the established patterns precisely so new sections feel native.

## Inputs to gather first
- **Model**: app + model name (e.g. `store.Product`). Confirm it exists or create it first.
- **Fields**: which fields appear in the list table and in the form.
- **Search/filters**: which fields are searchable; any status/category filters.
- **Extras**: image upload? rich text? ordering (drag-drop)? toggle action (publish/active)?

## The pattern (mirror existing code in `admin_panel/`)

### 1. Form — `admin_panel/forms.py`
Add a `ModelForm`. Match the style of `ProductForm`/`BlogPostForm`. Apply Tailwind widget classes so fields render with the design system, e.g.:
```python
class ThingForm(forms.ModelForm):
    class Meta:
        model = Thing
        fields = ['name', 'is_active', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLS}),
            # ...
        }
```
(Define/reuse an `INPUT_CLS = 'w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm'` constant if the file doesn't have one.)

### 2. Views — `admin_panel/views.py`
All views inherit `StaffRequiredMixin` (already defined at top of the file). Use the section-comment banner style (`# ─── Things ───`). Standard set:

- `AdminThingListView(StaffRequiredMixin, ListView)` — `paginate_by = 20`, `select_related`/`prefetch_related`, search via `request.GET.get('q')` + `Q(...)`, expose filter context.
- `AdminThingCreateView(StaffRequiredMixin, CreateView)` — `form_class`, `success_url = reverse_lazy('admin_panel:thing_list')`, set `page_title` in context. Set `form.instance.<owner>` in `form_valid` if needed (see `AdminPostCreateView` setting `author`).
- `AdminThingEditView(StaffRequiredMixin, UpdateView)` — same template, `page_title` = "ویرایش …".
- `AdminThingDeleteView(StaffRequiredMixin, View)` — `post()` does `get_object_or_404(...).delete()` then redirect. (Some existing delete views also accept GET → POST; prefer POST-only behind a confirm modal.)
- Optional toggle: `AdminThingToggleView` mirroring `AdminPostTogglePublishView`.

### 3. URLs — `admin_panel/urls.py`
Add under a section comment, names namespaced `admin_panel:`:
```python
path('things/', views.AdminThingListView.as_view(), name='thing_list'),
path('things/create/', views.AdminThingCreateView.as_view(), name='thing_create'),
path('things/<int:pk>/edit/', views.AdminThingEditView.as_view(), name='thing_edit'),
path('things/<int:pk>/delete/', views.AdminThingDeleteView.as_view(), name='thing_delete'),
```

### 4. Templates — `templates/admin_panel/<section>/`
Create `thing_list.html` and `thing_form.html`, both `{% extends 'admin_panel/base.html' %}`. Copy structure from the closest existing pair (e.g. `store/product_list.html` + `store/product_form.html`). Required pieces:
- `{% block page_header %}` with breadcrumb + `<h1>`.
- **List:** filter/search bar, a card-wrapped table in `overflow-x-auto`, row actions (edit link, delete via confirm modal), `{% include 'admin_panel/components/pagination.html' %}`, and a Persian empty state.
- **Form:** card layout, the form-error block, Tailwind inputs with labels, primary/secondary action buttons. Add `enctype="multipart/form-data"` if there are file fields.
- Invoke the **UI standards** in the `ui-ux-design` skill for all class/RTL/Persian decisions.

### 5. Sidebar link
Add a nav entry in `templates/admin_panel/components/sidebar.html` pointing at `{% url 'admin_panel:thing_list' %}` with a matching inline SVG icon and Persian label.

## Conventions checklist
- [ ] Every view guarded by `StaffRequiredMixin`
- [ ] URL names namespaced under `admin_panel:` and follow `thing_list/create/edit/delete`
- [ ] Templates extend `admin_panel/base.html`, all text Persian, RTL correct
- [ ] List has search/filter, pagination, empty state; table in `overflow-x-auto`
- [ ] Delete is POST behind `components/modal.html` confirm
- [ ] File fields → `enctype`; rich text → Quill; big selects → Tom Select; `order` field → SortableJS
- [ ] Numbers via `intcomma`/`fa-IR`, dates already Jalali
- [ ] Sidebar link added
- [ ] After wiring: remind to run `makemigrations`/`migrate` only if the model itself changed

## Quick verification
Run `python manage.py check` and load `/panel/things/` to confirm the section renders and the list/create/edit/delete cycle works.
