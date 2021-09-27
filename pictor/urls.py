from create_derivatives.views import (AWSUploadView, BagPreparerView,
                                      BagViewSet, CleanupView, JP2MakerView,
                                      ManifestMakerView, PDFMakerView)
from django.conf.urls import include, url
from django.contrib import admin
from rest_framework.routers import DefaultRouter
from rest_framework.schemas import get_schema_view

router = DefaultRouter()
router.register(r'bags', BagViewSet, basename='bag')

schema_view = get_schema_view(title="Pictor API")

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^prepare/', BagPreparerView.as_view(), name='bag-preparer'),
    url(r'^make-jp2/', JP2MakerView.as_view(), name='jp2-maker'),
    url(r'^make-pdf/', PDFMakerView.as_view(), name='pdf-maker'),
    url(r'^make-manifest/', ManifestMakerView.as_view(), name='manifest-maker'),
    url(r'^upload/', AWSUploadView.as_view(), name='aws-upload'),
    url(r'^cleanup/', CleanupView.as_view(), name='cleanup'),
    url(r'^schema/', schema_view, name='schema'),
    url(r'^admin/', admin.site.urls),
    url('status/', include('health_check.api.urls')),
]
