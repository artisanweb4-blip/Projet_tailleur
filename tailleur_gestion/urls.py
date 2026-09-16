from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Administration système Django & SaaS
    path('admin/', admin.site.urls),
    path('saas-admin/', include('saas_admin.urls', namespace='saas_admin')),

    # Application principale (Gestion des ateliers, landing page, etc.)
    path('', include('core.urls')),  # Inclut les URLs du module core
]

# Service des fichiers médias téléversés par les utilisateurs en mode développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)