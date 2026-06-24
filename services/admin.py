from django.contrib import admin

from .models import Service, Project, ProjectImage


class ProjectImageInline(admin.TabularInline):
    model = ProjectImage
    extra = 1
    verbose_name = 'تصویر پروژه'
    verbose_name_plural = 'تصاویر پروژه'


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'order', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'slug', 'description')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('order', 'is_active')
    readonly_fields = ('created_at',)
    ordering = ('order',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'location', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'slug', 'description', 'client', 'location')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('is_active',)
    readonly_fields = ('created_at',)
    inlines = [ProjectImageInline]
    ordering = ('-created_at',)


@admin.register(ProjectImage)
class ProjectImageAdmin(admin.ModelAdmin):
    list_display = ('project', 'caption', 'order')
    search_fields = ('project__title', 'caption')
    raw_id_fields = ('project',)
