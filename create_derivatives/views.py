from asterism.views import RoutineView
from rest_framework.viewsets import ModelViewSet

from .models import Bag
from .routines import (AWSUpload, BagPreparer, Cleanup, JP2Maker,
                       ManifestMaker, PDFMaker)
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


class JP2MakerView(RoutineView):
    """Runs the JP2Maker routine. Accepts POST requests only."""
    routine = JP2Maker


class PDFMakerView(RoutineView):
    """Runs the PDFMaker routine. Accepts POST requests only."""
    routine = PDFMaker


class ManifestMakerView(RoutineView):
    """Runs the ManifestMaker routine. Accepts POST requests only."""
    routine = ManifestMaker


class AWSUploadView(RoutineView):
    """Runs the AWSUpload routine. Accepts POST requests only."""
    routine = AWSUpload


class CleanupView(RoutineView):
    """Runs the Cleanup routine. Accepts POST requests only."""
    routine = Cleanup
