from django.contrib.auth.models import AbstractUser

from django.db import models


class Bag(models.Model):
    bag_path = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now=True)
    last_modified = models.DateTimeField(auto_now_add=True)


class User(AbstractUser):
    pass
