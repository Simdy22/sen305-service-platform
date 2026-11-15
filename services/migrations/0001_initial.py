from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ServiceRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("EQUIPMENT", "Equipment"),
                            ("SOFTWARE", "Software"),
                            ("ACCESS", "Access"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("OPEN", "Open"),
                            ("ASSIGNED", "Assigned"),
                            ("RESOLVED", "Resolved"),
                            ("CLOSED", "Closed"),
                        ],
                        default="OPEN",
                        max_length=20,
                    ),
                ),
                (
                    "priority",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (1, "Low"),
                            (2, "Medium"),
                            (3, "High"),
                            (4, "Urgent"),
                        ],
                        default=2,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="servicerequest",
            index=models.Index(
                fields=["category", "status"], name="svc_cat_status_idx"
            ),
        ),
    ]
