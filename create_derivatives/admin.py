from django.contrib import admin

from .models import Bag


@admin.register(Bag)
class BagAdmin(admin.ModelAdmin):
    """Django Admin for Bags."""
    pass
