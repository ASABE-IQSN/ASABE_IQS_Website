from django import forms
from .models import CrowdSubmission, Poll, PollOption


class CrowdSubmissionForm(forms.ModelForm):
    class Meta:
        model = CrowdSubmission
        fields = ['submission_type', 'text', 'photo']
        widgets = {
            'submission_type': forms.RadioSelect,
            'text': forms.Textarea(attrs={'maxlength': 280, 'rows': 4, 'placeholder': 'Share your thoughts… (280 chars max)'}),
        }

    def clean(self):
        cleaned = super().clean()
        stype = cleaned.get('submission_type')
        text = cleaned.get('text', '').strip()
        photo = cleaned.get('photo')
        if stype == 'comment' and not text:
            raise forms.ValidationError('Comment text is required.')
        if stype == 'photo' and not photo:
            raise forms.ValidationError('Please upload a photo.')
        return cleaned


class PollCreateForm(forms.ModelForm):
    class Meta:
        model = Poll
        fields = ['question', 'event']
        widgets = {
            'question': forms.TextInput(attrs={'placeholder': 'Enter poll question…', 'maxlength': 500}),
        }


class PollOptionFormSet(forms.BaseFormSet):
    pass


PollOptionInlineForm = forms.modelform_factory(
    PollOption,
    fields=['option_text', 'order'],
    widgets={
        'option_text': forms.TextInput(attrs={'placeholder': 'Option text…'}),
        'order': forms.NumberInput(attrs={'min': 0}),
    },
)
