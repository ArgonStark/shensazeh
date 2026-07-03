from django.db import migrations


def grant_defaults(apps, schema_editor):
    """Seed per-user permissions for existing active staff from their role.

    Runs against live models because it manipulates auth Permissions, which
    only exist after post_migrate; on a completely fresh database there are
    no StaffProfiles yet, so this is a no-op there.
    """
    from accounts.models import StaffProfile
    from admin_panel.permissions import apply_role_defaults

    for sp in StaffProfile.objects.select_related('user').filter(is_active_staff=True):
        if not sp.user.is_superuser and not sp.user.user_permissions.exists():
            apply_role_defaults(sp.user, sp.role)


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0002_alter_sitesetting_copyright_text_and_more'),
        ('accounts', '0001_initial'),
        ('finance', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(grant_defaults, migrations.RunPython.noop),
    ]
