#!/usr/bin/env python
"""Create a superuser for the project."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import User, StaffProfile

mobile = input('شماره موبایل (مثال: 09121234567): ').strip()
username = input('نام کاربری: ').strip()
email = input('ایمیل (برای ورود): ').strip()
password = input('رمز عبور: ').strip()
first_name = input('نام: ').strip()
last_name = input('نام خانوادگی: ').strip()

if User.objects.filter(mobile=mobile).exists():
    print(f'کاربر با شماره {mobile} قبلاً ثبت شده است.')
else:
    user = User.objects.create_superuser(
        username=username,
        mobile=mobile,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    StaffProfile.objects.create(user=user, role='manager')
    print(f'سوپریوزر "{username}" با موفقیت ساخته شد.')
