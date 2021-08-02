from create_derivatives.views import BagViewSet
from django.conf.urls import include, url
from django.contrib import admin
from rest_framework.routers import DefaultRouter
from rest_framework.schemas import get_schema_view

router = DefaultRouter()
router.register(r'bags', BagViewSet, basename='bag')

schema_view = get_schema_view(
    title="Pictor API",
)

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^schema/', schema_view, name='schema'),
    url(r'^admin/', admin.site.urls),
]
