from django.db import migrations

# Roles whose ROLE_DEFAULTS now include the new `visits` module.
ROLES_WITH_VISITS = ('manager', 'content')


def grant_visits(apps, schema_editor):
    """Give existing staff on visits-enabled roles the new panel permission.

    Additive on purpose: unlike `apply_role_defaults` this never resets the
    permissions an admin has hand-tuned since the staff member was created.
    On a fresh database there are no StaffProfiles yet, so this is a no-op.
    """
    from django.contrib.auth.models import Permission

    from accounts.models import StaffProfile

    try:
        perm = Permission.objects.get(
            content_type__app_label='dashboard', codename='view_sitevisit')
    except Permission.DoesNotExist:
        return

    staff = StaffProfile.objects.select_related('user').filter(
        is_active_staff=True, role__in=ROLES_WITH_VISITS)
    for sp in staff:
        if not sp.user.is_superuser:
            sp.user.user_permissions.add(perm)


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0005_sitesetting_invoice_sms_enabled_and_more'),
        ('accounts', '0001_initial'),
        ('dashboard', '0002_alter_sitevisit_ip_address_alter_sitevisit_path_and_more'),
    ]

    operations = [
        migrations.RunPython(grant_visits, migrations.RunPython.noop),
    ]
