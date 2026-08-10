from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),

    path("register/", views.register, name="register"),

    path(
        "login/",
        views.CustomLoginView.as_view(),
        name="login"
    ),

    path("logout/", views.auth_views.LogoutView.as_view(), name="logout"),

    path(
        "welcome/",
        views.character_intro,
        name="character_intro"
    ),

    path("inventory/", views.inventory, name="inventory"),

    path("item/new/", views.new_item, name="new_item"),

    path(
        "items/delete/",
        views.delete_multiple_items,
        name="delete_multiple_items"
    ),

    path(
        "items/reassign/",
        views.reassign_items,
        name="reassign_items"
    ),

    path("search/", views.search, name="search"),

    path(
        "settings/visibility/",
        views.toggle_visibility,
        name="toggle_visibility"
    ),

    path("characters/", views.characters, name="characters"),

    path(
        "characters/add/",
        views.characters_add,
        name="characters_add"
    ),

    path(
        "characters/<int:character_id>/default/",
        views.characters_set_default,
        name="characters_set_default"
    ),

    path(
        "characters/<int:character_id>/delete/",
        views.characters_delete,
        name="characters_delete"
    ),
]
