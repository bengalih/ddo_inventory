from django.contrib.auth import login as auth_login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import CharacterForm, ItemForm, RegisterForm
from .models import (
    Attribute,
    Character,
    Item,
    ItemAttribute,
    ItemType,
    MAX_ATTRIBUTES_PER_ITEM,
    MAX_ITEMS_PER_USER,
    SERVER_CHOICES,
)


MAX_SEARCH_CONDITIONS = 10
MAX_SEARCH_RESULTS = 200
MAX_CHARACTER_NAME_LENGTH = 50
MAX_ITEM_NAME_LENGTH = 100

OPERATOR_LOOKUPS = {
    "gte": "item_attributes__value__gte",
    "lte": "item_attributes__value__lte",
    "eq": "item_attributes__value",
    "gt": "item_attributes__value__gt",
    "lt": "item_attributes__value__lt",
}


def index(request):
    return render(request, "inventory/index.html")


class CustomLoginView(auth_views.LoginView):

    template_name = "inventory/login.html"

    def get_success_url(self):

        if not self.request.user.profile.has_seen_character_intro:
            return reverse("character_intro")

        return super().get_success_url()


def register(request):

    if request.method == "POST":

        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect("character_intro")

    else:
        form = RegisterForm()

    return render(
        request,
        "inventory/register.html",
        {"form": form}
    )


@login_required
def character_intro(request):

    profile = request.user.profile

    if not profile.has_seen_character_intro:
        profile.has_seen_character_intro = True
        profile.save()

    return render(request, "inventory/character_intro.html")


ALLOWED_SORTS = {
    "name": ["name"],
    "type": ["item_type__name"],
    "minimum_level": ["minimum_level"],
}


@login_required
def inventory(request):

    sort = request.GET.get("sort", "name")

    if sort not in ALLOWED_SORTS:
        sort = "name"

    direction = request.GET.get("direction", "asc")

    if direction not in ("asc", "desc"):
        direction = "asc"

    order_fields = ALLOWED_SORTS[sort]

    if direction == "desc":
        order_fields = [f"-{field}" for field in order_fields]

    # Always break ties on name so the ordering is stable.
    if "name" not in sort:
        order_fields = order_fields + ["name"]

    items = (
        Item.objects
        .filter(user=request.user)
        .select_related("item_type", "character")
        .prefetch_related("item_attributes__attribute")
        .order_by(*order_fields)
    )

    user_characters = Character.objects.filter(user=request.user)

    return render(
        request,
        "inventory/inventory.html",
        {
            "items": items,
            "current_sort": sort,
            "current_direction": direction,
            "is_public": request.user.profile.is_public,
            "user_characters": user_characters,
        }
    )


@login_required
@require_POST
def toggle_visibility(request):

    profile = request.user.profile
    profile.is_public = not profile.is_public
    profile.save()

    return redirect("inventory")


@login_required
def new_item(request):

    user_characters = Character.objects.filter(user=request.user)
    attributes = Attribute.objects.all()

    error = None

    if request.method == "POST":

        form = ItemForm(request.POST, user=request.user)

        auto_generate_name = (
            request.POST.get("auto_generate_name") == "on"
        )

        # Remember this choice for next time regardless of
        # whether the rest of the submission is valid.
        profile = request.user.profile
        if profile.auto_generate_item_names != auto_generate_name:
            profile.auto_generate_item_names = auto_generate_name
            profile.save()

        attribute_ids = request.POST.getlist("attribute_id")
        attribute_values = request.POST.getlist("attribute_value")

        submitted_attributes = []

        for index, attribute_id in enumerate(attribute_ids):

            if not attribute_id:
                continue

            value = ""

            if index < len(attribute_values):
                value = attribute_values[index].strip()

            submitted_attributes.append((attribute_id, value))

        if len(submitted_attributes) > MAX_ATTRIBUTES_PER_ITEM:
            error = (
                "Too many attributes. The maximum is "
                f"{MAX_ATTRIBUTES_PER_ITEM}."
            )

        validated_attributes = []

        if not error:

            seen_attribute_ids = set()

            for attribute_id, value in submitted_attributes:

                if attribute_id in seen_attribute_ids:
                    error = (
                        "The same attribute cannot be added "
                        "more than once."
                    )
                    break

                seen_attribute_ids.add(attribute_id)

                attribute = Attribute.objects.filter(
                    id=attribute_id
                ).first()

                if not attribute:
                    error = "Invalid attribute."
                    break

                if attribute.value_type == Attribute.VALUE_TYPE_NUMBER:

                    if not value:
                        error = (
                            f"{attribute.name} requires a "
                            "numeric value."
                        )
                        break

                    try:
                        numeric_value = int(value)
                    except ValueError:
                        error = (
                            f"{attribute.name} requires a "
                            "whole number."
                        )
                        break

                    if numeric_value <= 0:
                        error = (
                            f"{attribute.name} must have a "
                            "value greater than zero."
                        )
                        break

                    validated_attributes.append(
                        (attribute, numeric_value)
                    )

                else:
                    validated_attributes.append((attribute, None))

        if not error:

            item_count = Item.objects.filter(
                user=request.user
            ).count()

            if item_count >= MAX_ITEMS_PER_USER:
                error = (
                    "Your inventory has reached the maximum "
                    f"of {MAX_ITEMS_PER_USER} items."
                )

        if not error and form.is_valid():

            with transaction.atomic():

                item = form.save(commit=False)
                item.user = request.user

                if auto_generate_name:

                    parts = []

                    for attribute, value in validated_attributes:
                        if value is not None:
                            parts.append(
                                f"{attribute.name} +{value}"
                            )
                        else:
                            parts.append(attribute.name)

                    if parts:
                        generated_name = (
                            f"{item.item_type.name} "
                            f"({', '.join(parts)})"
                        )
                    else:
                        generated_name = item.item_type.name

                    item.name = generated_name[:100]

                item.save()

                for attribute, value in validated_attributes:
                    ItemAttribute.objects.create(
                        item=item,
                        attribute=attribute,
                        value=value
                    )

            return redirect("inventory")

    else:

        default_character = user_characters.filter(
            is_default=True
        ).first()

        form = ItemForm(
            user=request.user,
            initial={"character": default_character}
        )

        auto_generate_name = (
            request.user.profile.auto_generate_item_names
        )

    return render(
        request,
        "inventory/new_item.html",
        {
            "form": form,
            "attributes": attributes,
            "user_characters": user_characters,
            "error": error,
            "auto_generate_name": auto_generate_name,
        }
    )


@login_required
@require_POST
def delete_multiple_items(request):

    item_ids = request.POST.getlist("item_ids")

    if item_ids:
        Item.objects.filter(
            user=request.user,
            id__in=item_ids
        ).delete()

    return redirect("inventory")


@login_required
@require_POST
def reassign_items(request):

    item_ids = request.POST.getlist("item_ids")
    character_id = request.POST.get("character_id", "").strip()

    if not item_ids:
        return redirect("inventory")

    destination = None

    if character_id:

        destination = Character.objects.filter(
            id=character_id,
            user=request.user
        ).first()

        if not destination:
            return redirect("inventory")

    Item.objects.filter(
        user=request.user,
        id__in=item_ids
    ).update(character=destination)

    return redirect("inventory")


@login_required
def search(request):

    item_types = ItemType.objects.all()
    attributes = Attribute.objects.all()

    attribute_lookup = {
        str(attribute.id): attribute
        for attribute in attributes
    }

    error = None
    results = Item.objects.none()

    if request.GET:

        name = request.GET.get("name", "").strip()
        item_type_id = request.GET.get("item_type", "").strip()
        level_min = request.GET.get("level_min", "").strip()
        level_max = request.GET.get("level_max", "").strip()
        server = request.GET.get("server", "").strip()
        character_name = request.GET.get(
            "character_name", ""
        ).strip()

        qs = Item.objects.filter(
            Q(user=request.user) |
            Q(user__profile__is_public=True)
        )

        if not error and name:

            if len(name) > MAX_ITEM_NAME_LENGTH:
                error = (
                    f"Item name must be {MAX_ITEM_NAME_LENGTH} "
                    "characters or fewer."
                )
            else:
                # Django escapes % and _ automatically for
                # __icontains, so no manual LIKE-escaping needed
                # here (unlike the raw-SQL version).
                qs = qs.filter(name__icontains=name)

        if not error and item_type_id:

            if not ItemType.objects.filter(
                id=item_type_id
            ).exists():
                error = "Invalid item type."
            else:
                qs = qs.filter(item_type_id=item_type_id)

        if not error and server:

            if server not in dict(SERVER_CHOICES):
                error = "Invalid server."
            else:
                qs = qs.filter(character__server=server)

        if not error and character_name:

            if len(character_name) > MAX_CHARACTER_NAME_LENGTH:
                error = (
                    "Character name must be "
                    f"{MAX_CHARACTER_NAME_LENGTH} "
                    "characters or fewer."
                )
            else:
                qs = qs.filter(
                    character__name__icontains=character_name
                )

        if not error and level_min:
            try:
                qs = qs.filter(minimum_level__gte=int(level_min))
            except ValueError:
                error = "Minimum level must be a whole number."

        if not error and level_max:
            try:
                qs = qs.filter(minimum_level__lte=int(level_max))
            except ValueError:
                error = "Maximum level must be a whole number."

        attribute_ids = request.GET.getlist("attribute_id")
        operators = request.GET.getlist("operator")
        values = request.GET.getlist("value")

        if not error and len(attribute_ids) > MAX_SEARCH_CONDITIONS:
            error = (
                "Too many attribute filters. The maximum is "
                f"{MAX_SEARCH_CONDITIONS}."
            )

        if not error:

            for index, attribute_id in enumerate(attribute_ids):

                if not attribute_id:
                    continue

                attribute = attribute_lookup.get(attribute_id)

                if not attribute:
                    error = "Invalid attribute filter."
                    break

                if attribute.value_type == Attribute.VALUE_TYPE_NUMBER:

                    operator = (
                        operators[index]
                        if index < len(operators)
                        else ""
                    )

                    value = (
                        values[index].strip()
                        if index < len(values)
                        else ""
                    )

                    if operator not in OPERATOR_LOOKUPS:
                        error = (
                            f"Invalid comparison for "
                            f"{attribute.name}."
                        )
                        break

                    if not value:
                        error = (
                            f"{attribute.name} filter requires "
                            "a value."
                        )
                        break

                    try:
                        numeric_value = int(value)
                    except ValueError:
                        error = (
                            f"{attribute.name} filter requires "
                            "a whole number."
                        )
                        break

                    # A separate .filter() call per condition
                    # (rather than combining conditions into one
                    # call) gives each its own join, so
                    # "Seeker >= 5 AND Deadly >= 6" can be
                    # satisfied by two different ItemAttribute
                    # rows on the same item - matching the
                    # EXISTS-per-condition approach from the
                    # original raw-SQL version.
                    qs = qs.filter(
                        item_attributes__attribute_id=attribute_id,
                        **{OPERATOR_LOOKUPS[operator]: numeric_value}
                    )

                else:
                    qs = qs.filter(
                        item_attributes__attribute_id=attribute_id
                    )

        if not error:

            results = (
                qs
                .select_related("item_type", "character", "user")
                .prefetch_related("item_attributes__attribute")
                .distinct()
                .order_by("name")[:MAX_SEARCH_RESULTS]
            )

    # Pre-built as plain data because Django templates can't call
    # QueryDict.getlist("name") with an argument directly.
    existing_attribute_filters = []

    submitted_attribute_ids = request.GET.getlist("attribute_id")
    submitted_operators = request.GET.getlist("operator")
    submitted_values = request.GET.getlist("value")

    for index, attribute_id in enumerate(submitted_attribute_ids):
        existing_attribute_filters.append({
            "attribute_id": attribute_id,
            "operator": (
                submitted_operators[index]
                if index < len(submitted_operators)
                else ""
            ),
            "value": (
                submitted_values[index]
                if index < len(submitted_values)
                else ""
            ),
        })

    return render(
        request,
        "inventory/search.html",
        {
            "item_types": item_types,
            "attributes": attributes,
            "results": results,
            "error": error,
            "filters": request.GET,
            "servers": SERVER_CHOICES,
            "existing_attribute_filters": existing_attribute_filters,
        }
    )


@login_required
def characters(request):

    user_characters = Character.objects.filter(user=request.user)

    return render(
        request,
        "inventory/characters.html",
        {
            "characters": user_characters,
            "form": CharacterForm(),
        }
    )


@login_required
@require_POST
def characters_add(request):

    form = CharacterForm(request.POST, user=request.user)

    if form.is_valid():

        with transaction.atomic():

            is_first_character = not Character.objects.filter(
                user=request.user
            ).exists()

            character = form.save(commit=False)
            character.user = request.user
            character.is_default = is_first_character
            character.save()

            if is_first_character:
                # Bootstrap: attach any items this user created
                # before characters existed to their first one.
                Item.objects.filter(
                    user=request.user,
                    character__isnull=True
                ).update(character=character)

        return redirect("characters")

    user_characters = Character.objects.filter(user=request.user)

    return render(
        request,
        "inventory/characters.html",
        {
            "characters": user_characters,
            "form": form,
        }
    )


@login_required
@require_POST
def characters_set_default(request, character_id):

    character = get_object_or_404(
        Character,
        id=character_id,
        user=request.user
    )

    with transaction.atomic():
        Character.objects.filter(
            user=request.user
        ).update(is_default=False)

        character.is_default = True
        character.save()

    return redirect("characters")


@login_required
@require_POST
def characters_delete(request, character_id):

    character = get_object_or_404(
        Character,
        id=character_id,
        user=request.user
    )

    reassign_to = request.POST.get("reassign_to", "").strip()

    destination = None

    if reassign_to:

        destination = Character.objects.filter(
            id=reassign_to,
            user=request.user
        ).exclude(id=character.id).first()

        if not destination:

            user_characters = Character.objects.filter(
                user=request.user
            )

            return render(
                request,
                "inventory/characters.html",
                {
                    "characters": user_characters,
                    "form": CharacterForm(),
                    "error": "Invalid destination character.",
                }
            )

    with transaction.atomic():

        Item.objects.filter(character=character).update(
            character=destination
        )

        was_default = character.is_default

        character.delete()

        if was_default:

            remaining = Character.objects.filter(
                user=request.user
            ).order_by("id").first()

            if remaining:
                remaining.is_default = True
                remaining.save()

    return redirect("characters")
