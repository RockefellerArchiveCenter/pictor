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
