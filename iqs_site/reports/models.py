from django.db import models


class ReportPage(models.Model):
    page_id = models.AutoField(primary_key=True)
    report = models.ForeignKey(
        "events.Report",
        on_delete=models.CASCADE,
        related_name="pages",
    )
    page_number = models.IntegerField()  # 1-indexed

    class Meta:
        indexes = [
            models.Index(fields=["report", "page_number"]),
        ]
        ordering = ["report", "page_number"]

    def __str__(self):
        return f"Report {self.report_id} – page {self.page_number}"


class ReportChunk(models.Model):
    chunk_id = models.AutoField(primary_key=True)
    page = models.ForeignKey(
        ReportPage,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_index = models.IntegerField()  # ordering within the page
    text = models.TextField()
    # Bounding box in page-space coordinates (points).
    # Null for non-PDF formats (reserved for future use).
    bbox_x0 = models.FloatField(null=True, blank=True)
    bbox_y0 = models.FloatField(null=True, blank=True)
    bbox_x1 = models.FloatField(null=True, blank=True)
    bbox_y1 = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["page", "chunk_index"]

    def __str__(self):
        return f"Page {self.page_id} chunk {self.chunk_index}"


class PageMatch(models.Model):
    page_match_id = models.AutoField(primary_key=True)
    # page_a_id is always < page_b_id to avoid storing duplicate pairs.
    page_a = models.ForeignKey(
        ReportPage,
        on_delete=models.CASCADE,
        related_name="matches_as_a",
    )
    page_b = models.ForeignKey(
        ReportPage,
        on_delete=models.CASCADE,
        related_name="matches_as_b",
    )
    similarity = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["page_a", "page_b"], name="uniq_page_match"),
        ]
        indexes = [
            models.Index(fields=["-similarity"]),
        ]
        ordering = ["-similarity"]

    def __str__(self):
        return f"PageMatch ({self.page_a_id} <-> {self.page_b_id}, {self.similarity:.3f})"


class ChunkMatch(models.Model):
    chunk_match_id = models.AutoField(primary_key=True)
    page_match = models.ForeignKey(
        PageMatch,
        on_delete=models.CASCADE,
        related_name="chunk_matches",
    )
    chunk_a = models.ForeignKey(
        ReportChunk,
        on_delete=models.CASCADE,
        related_name="matches_as_a",
    )
    chunk_b = models.ForeignKey(
        ReportChunk,
        on_delete=models.CASCADE,
        related_name="matches_as_b",
    )
    similarity = models.FloatField()

    class Meta:
        ordering = ["-similarity"]

    def __str__(self):
        return f"ChunkMatch ({self.chunk_a_id} <-> {self.chunk_b_id}, {self.similarity:.3f})"


class AnalysisJob(models.Model):
    class Statuses(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    job_id = models.AutoField(primary_key=True)
    report_type = models.IntegerField(
        null=True, blank=True,
        help_text="Limit analysis to this report_type. Leave blank to compare all types.",
    )
    status = models.CharField(
        max_length=16,
        choices=Statuses.choices,
        default=Statuses.QUEUED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reports_found = models.IntegerField(default=0)
    reports_processed = models.IntegerField(default=0)
    pages_processed = models.IntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        rtype = f"type={self.report_type}" if self.report_type is not None else "all types"
        return f"AnalysisJob #{self.job_id} ({rtype}) – {self.status}"
