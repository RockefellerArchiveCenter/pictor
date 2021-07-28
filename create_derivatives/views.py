from rest_framework.viewsets import ModelViewSet

from .models import Bag
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
