from django.contrib import admin
from .models import Question, CompForm, FormQuestion, EventForm, FormResponse, QuestionResponse


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('question_id', 'question_text_truncated', 'question_type', 'created_at')

    def question_text_truncated(self, obj):
        return obj.question_text[:80]
    question_text_truncated.short_description = 'Question Text'


class FormQuestionInline(admin.TabularInline):
    model = FormQuestion
    extra = 1
    ordering = ('order',)


@admin.register(CompForm)
class CompFormAdmin(admin.ModelAdmin):
    list_display = ('form_id', 'name', 'created_at')
    inlines = [FormQuestionInline]


@admin.register(FormQuestion)
class FormQuestionAdmin(admin.ModelAdmin):
    list_display = ('form', 'question', 'order', 'required')


@admin.register(EventForm)
class EventFormAdmin(admin.ModelAdmin):
    list_display = ('event_form_id', 'event', 'form', 'is_open')
    list_filter = ('is_open', 'event')


@admin.register(FormResponse)
class FormResponseAdmin(admin.ModelAdmin):
    list_display = ('response_id', 'event_form', 'event_team', 'submitted_at', 'updated_at')


@admin.register(QuestionResponse)
class QuestionResponseAdmin(admin.ModelAdmin):
    list_display = ('question', 'answer_truncated')

    def answer_truncated(self, obj):
        return obj.answer[:80]
    answer_truncated.short_description = 'Answer'
