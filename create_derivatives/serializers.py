from rest_framework import serializers

from .models import Bag


class BagDetailSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Bag
        fields = '__all__'


class BagListSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Bag
        fields = [
            "url",
            "bag_identifier",
            "process_status",
            "created",
            "last_modified"]
