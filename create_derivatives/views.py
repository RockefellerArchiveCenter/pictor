from asterism.views import BaseServiceView, RoutineView
from rest_framework.viewsets import ModelViewSet

from .models import Bag
from .routines import (AWSUpload, BagPreparer, Cleanup, JP2Maker,
                       ManifestMaker, ManifestRecreator, PDFCompressor,
                       PDFMaker, PDFOCRer, TIFFPreparer)
from .serializers import BagDetailSerializer, BagListSerializer


class BagViewSet(ModelViewSet):
    """View set for Bags."""
    queryset = Bag.objects.all().order_by('last_modified')

    def get_serializer_class(self):
        """Sets the serializer class based on whether the view is a list or detail."""
        if getattr(self, "action") == "list":
            return BagListSerializer
        return BagDetailSerializer

    def create(self, request, *args, **kwargs):
        """Renames attributes in request data."""
        request.data["bag_identifier"] = request.data.get("identifier")
        request.data["data"] = request.data.get("bag_data")
        request.data["process_status"] = Bag.CREATED
        return super().create(request, *args, **kwargs)


class BagPreparerView(RoutineView):
    """Runs the BagPreparer routine. Accepts POST requests only."""
    routine = BagPreparer


class TIFFPreparerView(RoutineView):
    """Runs the TIFFPreparer routine. Accepts POST requests only."""
    routine = TIFFPreparer


class JP2MakerView(RoutineView):
    """Runs the JP2Maker routine. Accepts POST requests only."""
    routine = JP2Maker


class PDFMakerView(RoutineView):
    """Runs the PDFMaker routine. Accepts POST requests only."""
    routine = PDFMaker


class PDFCompressorView(RoutineView):
    """Runs the PDFCompressor routine. Accepts POST requests only."""
    routine = PDFCompressor


class PDFOCRerView(RoutineView):
    """Runs the PDFOCRer routine. Accepts POST requests only."""
    routine = PDFOCRer


class ManifestMakerView(RoutineView):
    """Runs the ManifestMaker routine. Accepts POST requests only."""
    routine = ManifestMaker


class ManifestRecreatorView(BaseServiceView):
    """Runs the ManifestRecreator routine. Accepts POST requests only."""
    routine = ManifestRecreator

    def get_service_response(self, request):
        if "manifest" not in request.POST:
            raise Exception("A manifest identifier is required.")
        return self.routine().run(request.POST["manifest"])


class AWSUploadView(RoutineView):
    """Runs the AWSUpload routine. Accepts POST requests only."""
    routine = AWSUpload


class CleanupView(RoutineView):
    """Runs the Cleanup routine. Accepts POST requests only."""
    routine = Cleanup
