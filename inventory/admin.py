from django.contrib import admin

from .models import Attribute, ItemType


@admin.register(ItemType)
class ItemTypeAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ["name", "value_type"]
    list_filter = ["value_type"]
    search_fields = ["name"]
