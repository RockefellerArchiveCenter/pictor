from asterism.views import PingView
from django.contrib import admin
from django.urls import include, re_path
from rest_framework.routers import DefaultRouter
from rest_framework.schemas import get_schema_view

from create_derivatives.views import (AWSUploadView, BagPreparerView,
                                      BagViewSet, CleanupView, JP2MakerView,
                                      ManifestMakerView, ManifestRecreatorView,
                                      PDFCompressorView, PDFMakerView,
                                      PDFOCRerView, TIFFPreparerView)

router = DefaultRouter()
router.register(r'bags', BagViewSet, basename='bag')

schema_view = get_schema_view(title="Pictor API")

urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(r'^prepare/', BagPreparerView.as_view(), name='bag-preparer'),
    re_path(r'^prepare-tiff/', TIFFPreparerView.as_view(), name='tiff-preparer'),
    re_path(r'^make-jp2/', JP2MakerView.as_view(), name='jp2-maker'),
    re_path(r'^make-pdf/', PDFMakerView.as_view(), name='pdf-maker'),
    re_path(r'^compress-pdf/', PDFCompressorView.as_view(), name='pdf-compressor'),
    re_path(r'^ocr-pdf/', PDFOCRerView.as_view(), name='pdf-ocrer'),
    re_path(r'^make-manifest/', ManifestMakerView.as_view(), name='manifest-maker'),
    re_path(r'^recreate-manifest/', ManifestRecreatorView.as_view(), name='manifest-recreator'),
    re_path(r'^upload/', AWSUploadView.as_view(), name='aws-upload'),
    re_path(r'^cleanup/', CleanupView.as_view(), name='cleanup'),
    re_path(r'^schema/', schema_view, name='schema'),
    re_path(r'^admin/', admin.site.urls),
    re_path('status/', PingView.as_view(), name='ping'),
]
