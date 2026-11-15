from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from .models import ServiceRequest


class OverdueFilter(admin.SimpleListFilter):
    """Overdue strategy: filter in the database using due_at + status.

    "Overdue" = due_at is in the past AND the request is not RESOLVED/CLOSED.
    This uses the (status, due_at) index added in migration 0002.
    """

    title = "due date"
    parameter_name = "overdue"

    def lookups(self, request, model_admin):
        return [
            ("yes", "Overdue"),
            ("due_24h", "Due in next 24 hours"),
            ("no_due", "No due date"),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        now = timezone.now()
        if value == "yes":
            return queryset.overdue(now)
        if value == "due_24h":
            return queryset.filter(
                due_at__gte=now, due_at__lt=now + timedelta(hours=24)
            ).exclude(status__in=ServiceRequest.RESOLVED_STATUSES)
        if value == "no_due":
            return queryset.filter(due_at__isnull=True)
        return queryset


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "category",
        "status",
        "priority",
        "due_at",
        "is_overdue",
        "resolved_at",
        "resolution_summary_short",
    )
    list_filter = ("status", "category", "priority", OverdueFilter, "due_at")
    search_fields = ("title", "description", "resolution_summary")
    ordering = ("-created_at",)
    # No readonly_fields for due_at/resolved_at/resolution_summary on purpose:
    # the model's clean() reports errors against those fields, so they must be
    # in the form for validation messages to display.

    @admin.display(boolean=True, description="Overdue")
    def is_overdue(self, obj):
        return bool(
            obj.due_at
            and obj.due_at < timezone.now()
            and obj.status not in ServiceRequest.RESOLVED_STATUSES
        )

    @admin.display(description="Resolution summary")
    def resolution_summary_short(self, obj):
        text = obj.resolution_summary or ""
        return text if len(text) <= 50 else text[:47] + "..."
