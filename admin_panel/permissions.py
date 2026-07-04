"""Module/action permission map for the staff panel.

The panel is organised in modules; each module maps to the Django model
permissions that a matrix checkbox (module × action) grants. Views declare a
single representative permission string (`permission_required`), while the
grant/revoke screen operates on whole module/action groups.
"""

from django.contrib.auth.models import Permission
from django.db.models import Q

ACTIONS = ['view', 'add', 'change', 'delete']
ACTION_LABELS = {'view': 'مشاهده', 'add': 'ایجاد', 'change': 'ویرایش', 'delete': 'حذف'}

MODULES = {
    'products': {
        'label': 'محصولات و دسته‌بندی‌ها',
        'models': ['store.product', 'store.category', 'store.productimage', 'store.productreview'],
    },
    'inventory': {
        'label': 'انبارداری',
        'models': ['inventory.inventoryentry'],
    },
    'invoices': {
        'label': 'فاکتورها و سفارشات',
        'models': ['orders.invoice', 'orders.invoiceitem', 'orders.order', 'orders.orderitem'],
    },
    'parties': {
        'label': 'طرف حساب‌ها و دفتر حساب',
        'models': ['parties.party', 'parties.partytag', 'parties.ledgerentry', 'parties.payment'],
    },
    'cheques': {
        'label': 'چک‌ها',
        'models': ['cheques.cheque', 'cheques.chequebook', 'cheques.chequeprintlayout'],
    },
    'blog': {
        'label': 'وبلاگ و اطلاعیه‌ها',
        'models': ['blog.blogpost', 'blog.blogcomment', 'blog.announcement'],
    },
    'services': {
        'label': 'خدمات و پروژه‌ها',
        'models': ['services.service', 'services.project', 'services.projectimage'],
    },
    'users': {
        'label': 'کاربران و کارکنان',
        'models': ['accounts.user', 'accounts.staffprofile'],
    },
    'cashflow': {
        'label': 'هزینه‌ها و درآمدها',
        'models': ['finance.cashtransaction', 'finance.expensecategory'],
    },
    'installments': {
        'label': 'فروش اقساطی',
        'models': ['installments.installmentplan', 'installments.installment'],
    },
    'calendar': {
        'label': 'تقویم مالی و یادآوری‌ها',
        'models': ['finance.reminder'],
    },
    'crm': {
        'label': 'پیامک و کمپین‌ها',
        'models': ['crm.campaign', 'crm.smslog'],
    },
    'settings': {
        'label': 'تنظیمات سایت',
        'models': ['admin_panel.sitesetting'],
        'actions': ['view', 'change'],
    },
    'audit': {
        'label': 'رویدادهای حسابرسی',
        'models': ['finance.auditlog'],
        'actions': ['view'],
    },
}

# Default grants applied when a staff member is created or their role changes.
ROLE_DEFAULTS = {
    'manager': {module: MODULES[module].get('actions', ACTIONS) for module in MODULES},
    'warehouse': {
        'products': ['view'],
        'inventory': ACTIONS,
        'invoices': ['view'],
    },
    'accountant': {
        'invoices': ACTIONS,
        'parties': ACTIONS,
        'cheques': ACTIONS,
        'cashflow': ACTIONS,
        'installments': ACTIONS,
        'calendar': ACTIONS,
        'inventory': ['view'],
        'products': ['view'],
        'users': ['view'],
        'audit': ['view'],
    },
    'sales': {
        'invoices': ['view', 'add', 'change'],
        'parties': ['view', 'add', 'change'],
        'cheques': ['view', 'add'],
        'installments': ['view', 'add'],
        'calendar': ['view', 'add', 'change'],
        'crm': ['view', 'add', 'change'],
        'products': ['view'],
        'inventory': ['view'],
        'users': ['view'],
    },
    'content': {
        'blog': ACTIONS,
        'services': ACTIONS,
        'products': ['view'],
    },
}


def module_actions(module):
    return MODULES[module].get('actions', ACTIONS)


def perm_labels(module, action):
    """('app_label', 'codename') pairs the module/action grants."""
    for model_label in MODULES[module]['models']:
        app, model = model_label.split('.')
        yield app, f'{action}_{model}'


def get_permissions(module, action):
    """Permission queryset for a module/action cell."""
    q = Q()
    for app, codename in perm_labels(module, action):
        q |= Q(content_type__app_label=app, codename=codename)
    return Permission.objects.filter(q)


def apply_role_defaults(user, role):
    """Reset user_permissions to the defaults of the given role."""
    perms = []
    for module, actions in ROLE_DEFAULTS.get(role, {}).items():
        for action in actions:
            if action in module_actions(module):
                perms.extend(get_permissions(module, action))
    user.user_permissions.set(perms)


def user_matrix(user):
    """{module: {action: granted}} — granted iff the user has every permission
    the cell covers (superusers implicitly have all)."""
    matrix = {}
    for module in MODULES:
        matrix[module] = {
            action: all(user.has_perm(f'{app}.{codename}')
                        for app, codename in perm_labels(module, action))
            for action in module_actions(module)
        }
    return matrix


def granted_cells(user):
    """Sorted 'module:action' list, for audit snapshots of a permission change."""
    return sorted(
        f'{module}:{action}'
        for module, row in user_matrix(user).items()
        for action, granted in row.items() if granted
    )
