from django.contrib import admin
from django.utils.html import format_html

from .models import AnalysisJob, ChunkMatch, ImageMatch, PageMatch, ReportChunk, ReportImage, ReportPage


@admin.register(ReportPage)
class ReportPageAdmin(admin.ModelAdmin):
    list_display = ["page_id", "report", "page_number", "chunk_count"]
    list_filter = ["report__report_type"]
    search_fields = ["report__report_id", "report__report_link"]
    ordering = ["report", "page_number"]

    def chunk_count(self, obj):
        return obj.chunks.count()
    chunk_count.short_description = "Chunks"


@admin.register(ReportChunk)
class ReportChunkAdmin(admin.ModelAdmin):
    list_display = ["chunk_id", "page", "chunk_index", "text_preview", "has_bbox"]
    list_filter = ["page__report__report_type"]
    search_fields = ["text"]
    ordering = ["page", "chunk_index"]

    def text_preview(self, obj):
        return obj.text[:80] + "…" if len(obj.text) > 80 else obj.text
    text_preview.short_description = "Text"

    def has_bbox(self, obj):
        return obj.bbox_x0 is not None
    has_bbox.boolean = True
    has_bbox.short_description = "BBox"


@admin.register(PageMatch)
class PageMatchAdmin(admin.ModelAdmin):
    list_display = ["page_match_id", "page_a", "page_b", "similarity_pct", "chunk_match_count"]
    list_filter = []
    search_fields = [
        "page_a__report__report_link",
        "page_b__report__report_link",
    ]
    ordering = ["-similarity"]
    readonly_fields = ["page_a", "page_b", "similarity"]

    def similarity_pct(self, obj):
        return format_html("<strong>{:.1f}%</strong>", obj.similarity * 100)
    similarity_pct.short_description = "Similarity"
    similarity_pct.admin_order_field = "similarity"

    def chunk_match_count(self, obj):
        return obj.chunk_matches.count()
    chunk_match_count.short_description = "Chunk matches"


@admin.register(ChunkMatch)
class ChunkMatchAdmin(admin.ModelAdmin):
    list_display = ["chunk_match_id", "page_match", "chunk_a", "chunk_b", "similarity_pct"]
    list_filter = []
    search_fields = [
        "chunk_a__text",
        "chunk_b__text",
    ]
    ordering = ["-similarity"]
    readonly_fields = ["page_match", "chunk_a", "chunk_b", "similarity"]

    def similarity_pct(self, obj):
        return format_html("{:.1f}%", obj.similarity * 100)
    similarity_pct.short_description = "Similarity"
    similarity_pct.admin_order_field = "similarity"


@admin.action(description="Queue a new analysis job for selected report type(s)")
def queue_analysis_job(modeladmin, request, queryset):
    from .tasks import run_plagiarism_analysis
    for job in queryset.filter(status=AnalysisJob.Statuses.QUEUED):
        run_plagiarism_analysis.delay(job.pk)


@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    list_display = [
        "job_id", "report_type_display", "status", "created_at",
        "reports_found", "reports_processed", "pages_processed", "images_processed",
    ]
    list_filter = ["status", "report_type"]
    ordering = ["-created_at"]
    readonly_fields = [
        "status", "created_at", "started_at", "completed_at",
        "reports_found", "reports_processed", "pages_processed", "images_processed", "error_message",
    ]
    actions = [queue_analysis_job]

    def report_type_display(self, obj):
        return obj.report_type if obj.report_type is not None else "All types"
    report_type_display.short_description = "Report type"


@admin.register(ReportImage)
class ReportImageAdmin(admin.ModelAdmin):
    list_display = ["image_id", "report", "page_number", "image_index", "phash", "width", "height"]
    list_filter = ["report__report_type"]
    search_fields = ["report__report_id", "report__report_link", "phash"]
    ordering = ["report", "page_number", "image_index"]
    readonly_fields = ["report", "page_number", "image_index", "phash", "width", "height"]


@admin.register(ImageMatch)
class ImageMatchAdmin(admin.ModelAdmin):
    list_display = ["image_match_id", "image_a", "image_b", "hamming_distance"]
    ordering = ["hamming_distance"]
    readonly_fields = ["image_a", "image_b", "hamming_distance"]
    search_fields = [
        "image_a__report__report_link",
        "image_b__report__report_link",
    ]
