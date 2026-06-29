from django.views.generic import ListView, DetailView

from .models import Service, Project


class ServiceListView(ListView):
    """List all active services."""
    model = Service
    template_name = 'services/service_list.html'
    context_object_name = 'services'

    def get_queryset(self):
        return Service.objects.filter(is_active=True)


class ServiceDetailView(DetailView):
    """Single service detail."""
    model = Service
    template_name = 'services/service_detail.html'
    context_object_name = 'service'
    slug_field = 'slug'

    def get_queryset(self):
        return Service.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['other_services'] = (
            Service.objects.filter(is_active=True)
            .exclude(pk=self.object.pk)[:5]
        )
        return context


class ProjectListView(ListView):
    """List all active projects."""
    model = Project
    template_name = 'services/project_list.html'
    context_object_name = 'projects'

    def get_queryset(self):
        return Project.objects.filter(is_active=True)


class ProjectDetailView(DetailView):
    """Single project with images."""
    model = Project
    template_name = 'services/project_detail.html'
    context_object_name = 'project'
    slug_field = 'slug'

    def get_queryset(self):
        return Project.objects.filter(is_active=True).prefetch_related('images')
