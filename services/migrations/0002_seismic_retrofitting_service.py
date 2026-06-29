from django.db import migrations


SERVICE = {
    'slug': 'moghavem-sazi-sakhteman',
    'title': 'مقاوم‌سازی ساختمان',
    'icon': 'bi-buildings-fill',
    'order': 1,
    'is_active': True,
    'description': (
        'مقاوم‌سازی و بهسازی لرزه‌ای سازه‌ها برای افزایش ایمنی و مقاومت ساختمان در '
        'برابر زلزله و بارهای جانبی. این خدمت با ارزیابی و بازرسی فنی سازه آغاز می‌شود و '
        'سپس راهکارهای تقویتی متناسب با شرایط بنا طراحی و اجرا می‌گردد.\n\n'
        'خدمات ما در این بخش شامل موارد زیر است:\n'
        '• ارزیابی و بازرسی فنی سازه‌های بتنی و فلزی و تعیین نقاط ضعف\n'
        '• تقویت با الیاف کربن (FRP) برای ستون‌ها، تیرها و دیوارها\n'
        '• اجرای ژاکت فلزی و بتنی جهت افزایش باربری اعضای سازه\n'
        '• اجرای بادبند فولادی و دیوار برشی برای مهار نیروهای جانبی\n'
        '• تقویت فونداسیون، اتصالات و ترمیم سازه‌های آسیب‌دیده\n\n'
        'تیم مهندسی ما با بهره‌گیری از مصالح استاندارد و روش‌های روز دنیا، ساختمان‌های '
        'مسکونی، تجاری و صنعتی را مطابق آیین‌نامه ۲۸۰۰ مقاوم‌سازی کرده و گواهی فنی '
        'لازم را ارائه می‌دهد.'
    ),
}


def add_service(apps, schema_editor):
    Service = apps.get_model('services', 'Service')
    Service.objects.update_or_create(
        slug=SERVICE['slug'],
        defaults={k: v for k, v in SERVICE.items() if k != 'slug'},
    )


def remove_service(apps, schema_editor):
    Service = apps.get_model('services', 'Service')
    Service.objects.filter(slug=SERVICE['slug']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_service, remove_service),
    ]
