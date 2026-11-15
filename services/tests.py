from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import connection
from django.forms import modelform_factory
from django.test import RequestFactory, TestCase
from django.utils import timezone

from .admin import ServiceRequestAdmin
from .models import ServiceRequest

S = ServiceRequest.Status
C = ServiceRequest.Category


def make(title="SYNTH test", **kw):
    """Build (unsaved) synthetic request; callers decide when to save."""
    kw.setdefault("category", C.EQUIPMENT)
    return ServiceRequest(title=title, **kw)


class OriginalBehaviourTests(TestCase):
    """Baseline behaviour that existed before the extension."""

    def test_defaults_and_str(self):
        r = make()
        r.save()
        self.assertEqual(r.status, S.OPEN)
        self.assertEqual(r.priority, ServiceRequest.Priority.MEDIUM)
        self.assertIsNotNone(r.created_at)
        self.assertIsNone(r.resolved_at)
        self.assertIn("SYNTH test", str(r))

    def test_open_request_needs_no_resolution_data(self):
        make(status=S.ASSIGNED).full_clean()  # must not raise


class DueDateTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.soon = make("SYNTH due soon", due_at=self.now + timedelta(hours=2))
        self.later = make("SYNTH due later", due_at=self.now + timedelta(days=5))
        self.none = make("SYNTH no due date")
        for r in (self.soon, self.later, self.none):
            r.save()

    def test_due_at_is_nullable(self):
        self.assertIsNone(self.none.due_at)

    def test_query_due_before_chosen_time(self):
        cutoff = self.now + timedelta(days=1)
        result = list(ServiceRequest.objects.due_before(cutoff))
        self.assertEqual(result, [self.soon])  # later + null excluded

    def test_overdue_excludes_resolved_and_future(self):
        past_open = make("SYNTH past open", due_at=self.now - timedelta(hours=3))
        past_done = make(
            "SYNTH past done",
            due_at=self.now - timedelta(hours=3),
            status=S.RESOLVED,
            resolved_at=self.now,
            resolution_summary="Replaced fuse.",
        )
        past_open.save()
        past_done.save()
        self.assertEqual(list(ServiceRequest.objects.overdue(self.now)), [past_open])

    def test_status_due_index_exists(self):
        with connection.cursor() as cur:
            constraints = connection.introspection.get_constraints(
                cur, ServiceRequest._meta.db_table
            )
        info = constraints.get("svc_status_due_idx")
        self.assertIsNotNone(info, "svc_status_due_idx missing")
        self.assertEqual(info["columns"], ["status", "due_at"])


class ResolutionRuleTests(TestCase):
    def test_resolved_without_data_fails_full_clean(self):
        for status in (S.RESOLVED, S.CLOSED):
            with self.subTest(status=status):
                with self.assertRaises(ValidationError) as ctx:
                    make(status=status).full_clean()
                self.assertIn("resolved_at", ctx.exception.message_dict)
                self.assertIn("resolution_summary", ctx.exception.message_dict)

    def test_resolved_missing_only_summary(self):
        r = make(status=S.RESOLVED, resolved_at=timezone.now())
        with self.assertRaises(ValidationError) as ctx:
            r.full_clean()
        self.assertEqual(list(ctx.exception.message_dict), ["resolution_summary"])

    def test_whitespace_summary_is_empty(self):
        r = make(
            status=S.CLOSED, resolved_at=timezone.now(), resolution_summary="   \n "
        )
        with self.assertRaises(ValidationError) as ctx:
            r.full_clean()
        self.assertIn("resolution_summary", ctx.exception.message_dict)

    def test_missing_only_resolved_at(self):
        r = make(status=S.CLOSED, resolution_summary="Done.")
        with self.assertRaises(ValidationError) as ctx:
            r.full_clean()
        self.assertEqual(list(ctx.exception.message_dict), ["resolved_at"])

    def test_valid_resolved_record_passes(self):
        for status in (S.RESOLVED, S.CLOSED):
            make(
                status=status,
                resolved_at=timezone.now(),
                resolution_summary="Recalibrated synthetic centrifuge.",
            ).full_clean()

    def test_save_enforces_rule_outside_admin(self):
        with self.assertRaises(ValidationError):
            make(status=S.RESOLVED).save()
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_plain_modelform_enforces_rule(self):
        Form = modelform_factory(
            ServiceRequest,
            fields=["title", "category", "status", "resolved_at", "resolution_summary"],
        )
        form = Form(
            {"title": "SYNTH f", "category": C.EQUIPMENT, "status": S.RESOLVED}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("resolution_summary", form.errors)
        self.assertIn("resolved_at", form.errors)


class AdminTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            "lab_admin", "lab@example.invalid", "not-a-real-password"
        )
        self.model_admin = ServiceRequestAdmin(ServiceRequest, AdminSite())
        now = timezone.now()
        self.overdue = make("SYNTH overdue", due_at=now - timedelta(days=1))
        self.future = make("SYNTH future", due_at=now + timedelta(days=3))
        self.overdue.save()
        self.future.save()

    def _changelist(self, **params):
        request = RequestFactory().get("/", params)
        request.user = self.admin_user
        return self.model_admin.get_changelist_instance(request)

    def test_due_at_and_summary_displayed(self):
        self.assertIn("due_at", self.model_admin.list_display)
        self.assertIn("resolution_summary_short", self.model_admin.list_display)
        self.assertIn("resolved_at", self.model_admin.list_display)

    def test_search_covers_resolution_summary(self):
        self.assertIn("resolution_summary", self.model_admin.search_fields)

    def test_overdue_filter(self):
        cl = self._changelist(overdue="yes")
        self.assertEqual(list(cl.queryset), [self.overdue])

    def test_is_overdue_column(self):
        self.assertTrue(self.model_admin.is_overdue(self.overdue))
        self.assertFalse(self.model_admin.is_overdue(self.future))
