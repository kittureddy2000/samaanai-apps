
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls', namespace='core')),
    path('oauth/', include('social_django.urls', namespace='social')),  # Social Auth URLs
    path('task_management/', include('task_management.urls')),
    path('spreturn/', include('spreturn.urls', namespace='spreturn')),

]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

