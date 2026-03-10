from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from events.models import Team
from .models import UserProfile

_current_year = date.today().year

STUDENT_YEAR_CHOICES = [('', 'Select a year...')] + [
    (y, str(y)) for y in range(_current_year + 4, 1997, -1)
]

ALUMNI_YEAR_CHOICES = [('', 'Select a year...')] + [
    (y, str(y)) for y in range(_current_year, 1997, -1)
]


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    role = forms.TypedChoiceField(
        choices=UserProfile.Role.choices,
        coerce=int,
        required=True,
        label="Role",
    )

    # Student fields
    team = forms.ModelChoiceField(
        queryset=Team.objects.all().order_by('team_name'),
        required=False,
        label="Team",
        empty_label="Select a team...",
    )
    graduation_year = forms.TypedChoiceField(
        choices=STUDENT_YEAR_CHOICES, coerce=int, required=False, label="Graduation Year",
        empty_value='',
    )

    # Sponsor fields
    company_name = forms.CharField(
        max_length=255, required=False, label="Company Name"
    )
    # sponsorship_level = forms.CharField(
    #     max_length=100, required=False, label="Sponsorship Level"
    # )

    # Alumni fields
    alumni_graduation_year = forms.TypedChoiceField(
        choices=ALUMNI_YEAR_CHOICES, coerce=int, required=False, label="Graduation Year",
        empty_value='',
    )
    years_participated = forms.IntegerField(
        required=False, min_value=0, label="Years Participated"
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    REQUIRED_BY_ROLE = {
        UserProfile.Role.STUDENT: ['team', 'graduation_year'],
        UserProfile.Role.ADVISOR: ['team'],
        UserProfile.Role.SPONSOR: ['company_name'],
        UserProfile.Role.ALUMNI: ['team', 'alumni_graduation_year', 'years_participated'],
        UserProfile.Role.SPECTATOR: [],
    }

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        for field_name in self.REQUIRED_BY_ROLE.get(role, []):
            value = cleaned.get(field_name)
            if not value and value != 0:
                self.add_error(field_name, 'This field is required.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.is_active = False
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data['role'],
                team=self.cleaned_data.get('team'),
                graduation_year=self.cleaned_data.get('graduation_year') or None,
                company_name=self.cleaned_data.get('company_name', ''),
                sponsorship_level=self.cleaned_data.get('sponsorship_level', ''),
                alumni_graduation_year=self.cleaned_data.get('alumni_graduation_year') or None,
                years_participated=self.cleaned_data.get('years_participated'),
            )
        return user
