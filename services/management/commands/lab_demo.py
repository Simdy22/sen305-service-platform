"""Synthetic-data demo for Task 1 (item 5) and Task 3 (query analysis).

Usage:  python manage.py lab_demo
Only synthetic laboratory data is created (titles start with "SYNTH-").
Output is also saved to evidence/query_evidence.txt for your write-up.
"""
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from services.models import ServiceRequest

S = ServiceRequest.Status
C = ServiceRequest.Category
P = ServiceRequest.Priority

# (category, status, priority, age_in_hours, due_in_hours or None)
SEED = [
    (C.EQUIPMENT, S.OPEN, P.URGENT, 48, 6),
    (C.EQUIPMENT, S.OPEN, P.HIGH, 40, 30),
    (C.EQUIPMENT, S.ASSIGNED, P.HIGH, 36, -4),
    (C.EQUIPMENT, S.ASSIGNED, P.LOW, 30, 72),
    (C.EQUIPMENT, S.OPEN, P.MEDIUM, 24, None),
    (C.EQUIPMENT, S.RESOLVED, P.MEDIUM, 60, -20),
    (C.EQUIPMENT, S.RESOLVED, P.LOW, 70, None),
    (C.SOFTWARE, S.OPEN, P.URGENT, 20, 2),
    (C.SOFTWARE, S.ASSIGNED, P.MEDIUM, 18, 48),
    (C.SOFTWARE, S.OPEN, P.LOW, 12, None),
    (C.SOFTWARE, S.RESOLVED, P.HIGH, 50, -10),
    (C.SOFTWARE, S.ASSIGNED, P.HIGH, 8, 12),
]


class Command(BaseCommand):
    help = "Seed synthetic requests, run due-date and query-analysis demos."

    def handle(self, *args, **options):
        lines = []

        def out(text=""):
            lines.append(str(text))
            self.stdout.write(str(text))

        now = timezone.now()
        ServiceRequest.objects.filter(title__startswith="SYNTH-").delete()

        for i, (cat, status, prio, age_h, due_h) in enumerate(SEED, start=1):
            kw = {}
            if status == S.RESOLVED:
                kw["resolved_at"] = now - timedelta(hours=1)
                kw["resolution_summary"] = "Synthetic fix applied and verified."
            r = ServiceRequest(
                title=f"SYNTH-{i:03d} {cat.label} request",
                category=cat,
                status=status,
                priority=prio,
                due_at=None if due_h is None else now + timedelta(hours=due_h),
                **kw,
            )
            r.save()
            # created_at is auto_now_add, so spread it with update() afterwards
            ServiceRequest.objects.filter(pk=r.pk).update(
                created_at=now - timedelta(hours=age_h)
            )

        out(f"Database vendor: {connection.vendor}")
        out(f"Synthetic rows: {ServiceRequest.objects.filter(title__startswith='SYNTH-').count()}")

        # ---- Task 1, item 5: two requests, different due dates ----
        out("\n=== Task 1: requests due before a chosen time ===")
        a = ServiceRequest.objects.get(title__startswith="SYNTH-001")
        b = ServiceRequest.objects.get(title__startswith="SYNTH-002")
        cutoff = now + timedelta(hours=12)
        out(f"{a.title}: due_at={a.due_at:%Y-%m-%d %H:%M}")
        out(f"{b.title}: due_at={b.due_at:%Y-%m-%d %H:%M}")
        out(f"Chosen cutoff: {cutoff:%Y-%m-%d %H:%M}")
        due_qs = ServiceRequest.objects.due_before(cutoff).filter(
            title__startswith="SYNTH-"
        )
        out(f"SQL: {due_qs.query}")
        for r in due_qs.order_by("due_at"):
            out(f"  -> {r.title} due {r.due_at:%Y-%m-%d %H:%M} [{r.status}]")

        # ---- Task 3: query analysis ----
        out("\n=== Task 3: open/assigned EQUIPMENT ordered by priority, created ===")
        qs = (
            ServiceRequest.objects.filter(category=C.EQUIPMENT)
            .open_or_assigned()
            .order_by("-priority", "created_at")
        )
        out("queryset.query:")
        out(str(qs.query))
        out("\nResults:")
        for r in qs:
            out(f"  {r.title} | {r.status} | priority={r.priority} | created={r.created_at:%m-%d %H:%M}")
        out("\nqueryset.explain():")
        out(qs.explain())

        out("\nIndexes on table (from DB introspection):")
        with connection.cursor() as cur:
            cons = connection.introspection.get_constraints(
                cur, ServiceRequest._meta.db_table
            )
        for name, info in cons.items():
            if info.get("index") or info.get("primary_key"):
                out(f"  {name}: {info['columns']}")

        path = Path(settings.BASE_DIR) / "evidence" / "query_evidence.txt"
        path.parent.mkdir(exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"\nSaved to {path}"))
