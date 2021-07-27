from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from .models import Bag


class ViewTestCase(TestCase):
    """Tests Views."""
    fixtures = ["created.json"]

    def setUp(self):
        self.factory = APIRequestFactory()

    def assert_status_code(
            self, method, url, expected_status, data=None, **kwargs):
        """Asserts that a URL returns an expected HTTP status code."""
        response = getattr(self.client, method)(url, data, **kwargs)
        self.assertEqual(
            expected_status, response.status_code,
            "Expected status code {} but got {}".format(expected_status, response.status_code))

    def test_bagviewset(self):
        """Asserts BagViewSet views return expected responses."""
        self.assert_status_code("get", reverse("bag-list"), 200)
        for bag in Bag.objects.all():
            self.assert_status_code(
                "get",
                reverse(
                    "bag-detail",
                    kwargs={
                        "pk": bag.pk}),
                200)
        data = {
            "bag_data": {
                "uri": "foo"},
            "origin": "digitization",
            "identifier": "foo"}
        self.assert_status_code(
            "post",
            reverse("bag-list"),
            201,
            data=data,
            content_type="application/json")
