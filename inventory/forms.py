from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import (
    Character,
    Item,
    MAX_MINIMUM_LEVEL,
    MIN_MINIMUM_LEVEL,
)


class RegisterForm(UserCreationForm):

    class Meta:
        model = User
        fields = ["username", "password1", "password2"]


# (None) plus every level from MIN to MAX, matching the original
# app's dropdown.
MINIMUM_LEVEL_CHOICES = (
    [("", "(None)")] +
    [
        (level, level)
        for level in range(MIN_MINIMUM_LEVEL, MAX_MINIMUM_LEVEL + 1)
    ]
)


class ItemForm(forms.ModelForm):

    minimum_level = forms.TypedChoiceField(
        choices=MINIMUM_LEVEL_CHOICES,
        coerce=int,
        required=False,
        empty_value=None
    )

    class Meta:
        model = Item
        fields = [
            "name",
            "item_type",
            "character",
            "minimum_level",
            "description",
        ]
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 4, "cols": 60, "maxlength": 2000}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Scoping the queryset to this user means Django's own
        # ModelChoiceField validation rejects anyone else's
        # character id automatically - no manual ownership
        # check needed.
        self.fields["character"].queryset = (
            Character.objects.filter(user=user)
        )
        self.fields["character"].required = False
        self.fields["character"].empty_label = (
            "-- No Character --"
        )

        self.fields["item_type"].empty_label = (
            "-- Select Type --"
        )


class CharacterForm(forms.ModelForm):

    class Meta:
        model = Character
        fields = ["name", "server"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get("name")
        server = cleaned_data.get("server")

        if name and server:
            # Global, not per-user: DDO itself enforces character
            # names as unique per-server across the whole server,
            # not just within one account.
            exists = Character.objects.filter(
                name=name,
                server=server
            ).exists()

            if exists:
                raise forms.ValidationError(
                    "That character name is already taken on "
                    "that server."
                )

        return cleaned_data
