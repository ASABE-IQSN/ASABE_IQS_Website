from django import forms

class TeamProfileEditForm(forms.Form):
    nickname = forms.CharField(required=False, max_length=255)
    bio = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 5}), max_length=255)
    website = forms.CharField(required=False, max_length=255)

    instagram = forms.CharField(required=False, max_length=255, help_text="Handle only (no @)")
    facebook = forms.CharField(required=False, max_length=255)
    linkedin = forms.CharField(required=False, max_length=255)
    youtube = forms.CharField(required=False, max_length=255)

    def clean_instagram(self):
        v = (self.cleaned_data.get("instagram") or "").strip()
        return v.lstrip("@")

    def clean_website(self):
        v = (self.cleaned_data.get("website") or "").strip()
        return v

    def clean_linkedin(self):
        return (self.cleaned_data.get("linkedin") or "").strip()

    def clean_youtube(self):
        return (self.cleaned_data.get("youtube") or "").strip()

class TractorProfileEditForm(forms.Form):
    nickname = forms.CharField(required=False, max_length=255)
    bio = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 5}), max_length=255)
    website = forms.CharField(required=False, max_length=255)

    instagram = forms.CharField(required=False, max_length=255)
    facebook = forms.CharField(required=False, max_length=255)
    linkedin = forms.CharField(required=False, max_length=255)
    youtube = forms.CharField(required=False, max_length=255)

    def clean_instagram(self):
        v = (self.cleaned_data.get("instagram") or "").strip()
        return v.lstrip("@")