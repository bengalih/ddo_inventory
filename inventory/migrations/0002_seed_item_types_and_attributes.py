from django.db import migrations


ITEM_TYPES = [
    "Helmet",
    "Necklace",
    "Trinket",
    "Cloak",
    "Belt",
    "Gloves",
    "Boots",
    "Bracers",
    "Ring",
    "Goggles",
    "Armor",
    "Shield",
    "Weapon",
    "Bow",
    "Quiver",
]

ATTRIBUTES = [
    ("Deadly", "number"),
    ("Seeker", "number"),
    ("Accuracy", "number"),
    ("Insightful Dexterity", "number"),
    ("Ghost Touch", "none"),
    ("Ghostly", "none"),
    ("Feather Falling", "none"),
    ("Red Augment Slot", "none"),
    ("Yellow Augment Slot", "none"),
    ("Blue Augment Slot", "none"),
]


def seed_data(apps, schema_editor):

    ItemType = apps.get_model("inventory", "ItemType")
    Attribute = apps.get_model("inventory", "Attribute")

    for name in ITEM_TYPES:
        ItemType.objects.get_or_create(name=name)

    for name, value_type in ATTRIBUTES:
        Attribute.objects.get_or_create(
            name=name,
            defaults={"value_type": value_type}
        )


def remove_seed_data(apps, schema_editor):

    ItemType = apps.get_model("inventory", "ItemType")
    Attribute = apps.get_model("inventory", "Attribute")

    ItemType.objects.filter(name__in=ITEM_TYPES).delete()

    Attribute.objects.filter(
        name__in=[name for name, _ in ATTRIBUTES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_data, remove_seed_data),
    ]
