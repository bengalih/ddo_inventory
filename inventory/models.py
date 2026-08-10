from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


DDO_SERVERS = [
    "Cormyr",
    "Moonsea",
    "Shadowdale",
    "Thrane",
]

SERVER_CHOICES = [(server, server) for server in DDO_SERVERS]

MIN_MINIMUM_LEVEL = 1
MAX_MINIMUM_LEVEL = 36

MAX_ITEMS_PER_USER = 1000
MAX_ATTRIBUTES_PER_ITEM = 30


class Profile(models.Model):
    """
    Extends the built-in User with app-specific fields.
    Auto-created for every User via the signal below, so it
    exists whether the user registered through the app or was
    created with `manage.py createsuperuser`.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    is_public = models.BooleanField(
        default=True,
        help_text=(
            "If on, this user's items are visible to other "
            "users in search."
        )
    )

    has_seen_character_intro = models.BooleanField(
        default=False,
        help_text=(
            "Set once the one-time 'you can create a "
            "character, or skip for now' screen has been "
            "shown after login/registration."
        )
    )

    auto_generate_item_names = models.BooleanField(
        default=False,
        help_text=(
            "Remembers this user's last choice for the "
            "'auto-generate name from type and attributes' "
            "checkbox on the Add Item form."
        )
    )

    def __str__(self):
        return f"Profile({self.user.username})"


@receiver(post_save, sender=User)
def create_profile_for_new_user(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


class ItemType(models.Model):

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Attribute(models.Model):

    VALUE_TYPE_NUMBER = "number"
    VALUE_TYPE_NONE = "none"

    VALUE_TYPE_CHOICES = [
        (VALUE_TYPE_NUMBER, "Number"),
        (VALUE_TYPE_NONE, "Presence only (no value)"),
    ]

    name = models.CharField(max_length=100, unique=True)

    value_type = models.CharField(
        max_length=10,
        choices=VALUE_TYPE_CHOICES,
        default=VALUE_TYPE_NUMBER
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Character(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="characters"
    )

    name = models.CharField(max_length=50)

    server = models.CharField(
        max_length=20,
        choices=SERVER_CHOICES
    )

    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "server"],
                name="unique_character_name_per_server"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.server})"


class Item(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="items"
    )

    character = models.ForeignKey(
        Character,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items"
    )

    name = models.CharField(max_length=100, blank=True)

    # PROTECT: mirrors the "can't delete an item type that's
    # still in use" rule from the original admin panel, enforced
    # at the database-relationship level rather than hand-checked
    # in a view.
    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.PROTECT,
        related_name="items"
    )

    minimum_level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(MIN_MINIMUM_LEVEL),
            MaxValueValidator(MAX_MINIMUM_LEVEL)
        ]
    )

    description = models.TextField(max_length=2000, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ItemAttribute(models.Model):

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="item_attributes"
    )

    # PROTECT: mirrors the "can't delete an attribute that's
    # still in use" rule from the original admin panel.
    attribute = models.ForeignKey(
        Attribute,
        on_delete=models.PROTECT,
        related_name="item_attributes"
    )

    # Stored as a real integer (unlike the original schema's
    # TEXT column) so numeric search comparisons are correct
    # without needing an explicit CAST - "9" vs "10" as strings
    # would otherwise sort/compare lexicographically.
    value = models.IntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "attribute"],
                name="unique_attribute_per_item"
            )
        ]

    def __str__(self):
        return f"{self.item.name}: {self.attribute.name}"
