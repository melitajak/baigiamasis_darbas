from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),       # Admin site
    path('tools/', include('tools.urls')), # Include URLs from the tools app
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)