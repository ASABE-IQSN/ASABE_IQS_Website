from django.contrib import admin
from .models import (
    Question, CompForm, FormQuestion, EventForm, FormResponse, QuestionResponse,
    QuestionGroup, GroupQuestion, TeamQuestionAssignment, QuestionSwap,
)


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


class GroupQuestionInline(admin.TabularInline):
    model = GroupQuestion
    extra = 1
    ordering = ('display_order',)


class QuestionGroupInline(admin.StackedInline):
    model = QuestionGroup
    extra = 0
    show_change_link = True


@admin.register(CompForm)
class CompFormAdmin(admin.ModelAdmin):
    list_display = ('form_id', 'name', 'created_at')
    inlines = [FormQuestionInline, QuestionGroupInline]


@admin.register(FormQuestion)
class FormQuestionAdmin(admin.ModelAdmin):
    list_display = ('form', 'question', 'order', 'required')


@admin.register(QuestionGroup)
class QuestionGroupAdmin(admin.ModelAdmin):
    list_display = ('group_id', 'form', 'name', 'num_assigned', 'order')
    list_filter = ('form',)
    inlines = [GroupQuestionInline]


@admin.register(TeamQuestionAssignment)
class TeamQuestionAssignmentAdmin(admin.ModelAdmin):
    list_display = ('assignment_id', 'event_team', 'group', 'question', 'display_order')
    list_filter = ('group__form', 'group')
    readonly_fields = ('assignment_id', 'event_team', 'group', 'question', 'display_order')

    def has_add_permission(self, request):
        return False


@admin.register(EventForm)
class EventFormAdmin(admin.ModelAdmin):
    list_display = ('event_form_id', 'event', 'form', 'is_open')
    list_filter = ('is_open', 'event')


@admin.register(FormResponse)
class FormResponseAdmin(admin.ModelAdmin):
    list_display = ('response_id', 'event_form', 'event_team', 'submitted_at', 'updated_at')


@admin.register(QuestionResponse)
class QuestionResponseAdmin(admin.ModelAdmin):
    list_display = ('question', 'answer_truncated', 'flagged', 'flagged_by', 'flagged_at')
    list_filter = ('flagged',)

    def answer_truncated(self, obj):
        return obj.answer[:80]
    answer_truncated.short_description = 'Answer'


@admin.register(QuestionSwap)
class QuestionSwapAdmin(admin.ModelAdmin):
    list_display = ('swap_id', 'event_team', 'group', 'old_question', 'new_question', 'swapped_at', 'is_flag_driven')
    list_filter = ('is_flag_driven', 'group__form')
    readonly_fields = ('swap_id', 'event_team', 'event_form', 'group', 'old_question', 'new_question', 'swapped_at', 'swapped_by', 'is_flag_driven')

    def has_add_permission(self, request):
        return False
