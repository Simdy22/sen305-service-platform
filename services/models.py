from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ServiceRequestQuerySet(models.QuerySet):
    """Reusable queries so Admin, tests and commands share one definition."""

    def open_or_assigned(self):
        return self.filter(
            status__in=[ServiceRequest.Status.OPEN, ServiceRequest.Status.ASSIGNED]
        )

    def due_before(self, moment):
        """Requests that have a due date earlier than `moment`."""
        return self.filter(due_at__isnull=False, due_at__lt=moment)

    def overdue(self, now=None):
        """Past due and not yet resolved/closed."""
        now = now or timezone.now()
        return self.due_before(now).exclude(
            status__in=ServiceRequest.RESOLVED_STATUSES
        )


class ServiceRequest(models.Model):
    class Category(models.TextChoices):
        EQUIPMENT = "EQUIPMENT", "Equipment"
        SOFTWARE = "SOFTWARE", "Software"
        ACCESS = "ACCESS", "Access"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        ASSIGNED = "ASSIGNED", "Assigned"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    class Priority(models.IntegerChoices):
        LOW = 1, "Low"
        MEDIUM = 2, "Medium"
        HIGH = 3, "High"
        URGENT = 4, "Urgent"

    # Statuses that must carry resolution data.
    RESOLVED_STATUSES = (Status.RESOLVED, Status.CLOSED)

    # --- original fields (migration 0001) ---
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    priority = models.PositiveSmallIntegerField(
        choices=Priority.choices, default=Priority.MEDIUM
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # --- extension fields (migration 0002) ---
    due_at = models.DateTimeField(null=True, blank=True)
    resolution_summary = models.TextField(blank=True)

    objects = ServiceRequestQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["category", "status"], name="svc_cat_status_idx"),
            models.Index(fields=["status", "due_at"], name="svc_status_due_idx"),
        ]

    def __str__(self):
        return f"#{self.pk} {self.title}"

    def clean(self):
        """Domain rule: RESOLVED/CLOSED requests need resolved_at and a summary.

        Lives on the model (not Admin) so every caller gets it: Admin forms,
        scripts, services and tests.
        """
        super().clean()
        errors = {}
        if self.status in self.RESOLVED_STATUSES:
            if self.resolved_at is None:
                errors["resolved_at"] = (
                    "resolved_at is required when status is RESOLVED or CLOSED."
                )
            if not (self.resolution_summary or "").strip():
                errors["resolution_summary"] = (
                    "A non-empty resolution summary is required when status "
                    "is RESOLVED or CLOSED."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Enforce the rule on every save(). Note: bulk_create() and
        # QuerySet.update() bypass save(), so use save() for lifecycle changes.
        self.full_clean()
        super().save(*args, **kwargs)
