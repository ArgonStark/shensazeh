from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, OTPCode, StaffProfile


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    extra = 0
    verbose_name = 'پروفایل کارمند'
    verbose_name_plural = 'پروفایل کارمندان'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('mobile', 'get_full_name', 'province', 'city', 'is_active', 'is_staff', 'created_at')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'province')
    search_fields = ('mobile', 'first_name', 'last_name', 'username', 'city')
    ordering = ('-created_at',)
    inlines = [StaffProfileInline]

    fieldsets = (
        (None, {'fields': ('mobile', 'username', 'password')}),
        ('اطلاعات شخصی', {'fields': ('first_name', 'last_name', 'email')}),
        ('آدرس', {'fields': ('province', 'city', 'address', 'postal_code')}),
        ('دسترسی‌ها', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('mobile', 'username', 'password1', 'password2'),
        }),
    )


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ('mobile', 'code', 'is_used', 'created_at')
    list_filter = ('is_used', 'created_at')
    search_fields = ('mobile', 'code')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'is_active_staff')
    list_filter = ('role', 'is_active_staff')
    search_fields = ('user__mobile', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user',)
