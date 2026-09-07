from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import RedirectView
from django.templatetags.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('', include('attendance.urls')),

    # Root Favicon & Web Manifest Shortcuts
    path('favicon.ico', RedirectViewwz.as_view(url=static('favicon/favicon.ico'), permanent=True)),
    path('favicon-96x96.png', RedirectView.as_view(url=static('favicon/favicon-96x96.png'), permanent=True)),
    path('favicon.svg', RedirectView.as_view(url=static('favicon/favicon.svg'), permanent=True)),
    path('apple-touch-icon.png', RedirectView.as_view(url=static('favicon/apple-touch-icon.png'), permanent=True)),
    path('site.webmanifest', RedirectView.as_view(url=static('favicon/site.webmanifest'), permanent=True)),
    path('web-app-manifest-192x192.png', RedirectView.as_view(url=static('favicon/web-app-manifest-192x192.png'), permanent=True)),
    path('web-app-manifest-512x512.png', RedirectView.as_view(url=static('favicon/web-app-manifest-512x512.png'), permanent=True)),
]
