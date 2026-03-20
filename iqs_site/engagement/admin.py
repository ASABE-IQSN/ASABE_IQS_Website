from django.contrib import admin
from .models import CrowdSubmission, ReactionAggregate, Poll, PollOption, FanVoteCategory, FanVote


class PollOptionInline(admin.TabularInline):
    model = PollOption
    extra = 2
    fields = ['option_text', 'order', 'vote_count']
    readonly_fields = ['vote_count']


@admin.register(CrowdSubmission)
class CrowdSubmissionAdmin(admin.ModelAdmin):
    list_display = ['submission_id', 'submitted_by', 'submission_type', 'status', 'event', 'created_at']
    list_filter = ['status', 'submission_type', 'event']
    readonly_fields = ['submission_id', 'created_at', 'reviewed_at']
    search_fields = ['text', 'submitted_by__username']


@admin.register(ReactionAggregate)
class ReactionAggregateAdmin(admin.ModelAdmin):
    list_display = ['aggregate_id', 'event', 'emoji', 'count', 'last_updated']
    list_filter = ['event', 'emoji']
    readonly_fields = ['last_updated']


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ['poll_id', 'question', 'status', 'event', 'created_by', 'created_at']
    list_filter = ['status', 'event']
    readonly_fields = ['poll_id', 'created_at', 'activated_at']
    inlines = [PollOptionInline]


@admin.register(FanVoteCategory)
class FanVoteCategoryAdmin(admin.ModelAdmin):
    list_display = ['category_id', 'name', 'event', 'is_active', 'created_at']
    list_filter = ['event', 'is_active']
    readonly_fields = ['category_id', 'created_at']


@admin.register(FanVote)
class FanVoteAdmin(admin.ModelAdmin):
    list_display = ['vote_id', 'category', 'team', 'session_key', 'created_at']
    list_filter = ['category']
    readonly_fields = ['vote_id', 'created_at']
