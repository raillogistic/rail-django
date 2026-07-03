"""Add reusable reporting audience, origin, and authoring audit fields."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_dataset_roles(apps, schema_editor):
    Dataset = apps.get_model("rail_django", "ReportingDataset")
    for dataset in Dataset.objects.all().iterator():
        dataset.allowed_roles = list(
            (dataset.metadata or {}).get("allowed_roles") or []
        )
        dataset.save(update_fields=["allowed_roles"])


class Migration(migrations.Migration):
    dependencies = [
        ("rail_django", "0006_reportingvisualizationtemplate_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="reportingdataset",
            name="allowed_roles",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Roles autorises a consulter ce jeu de donnees.",
                verbose_name="Roles autorises",
            ),
        ),
        migrations.AddField(
            model_name="reportingdataset",
            name="origin",
            field=models.CharField(
                choices=[("catalog", "Catalogue"), ("studio", "Studio")],
                default="catalog",
                max_length=20,
                verbose_name="Origine",
            ),
        ),
        migrations.AddField(
            model_name="reportingdataset",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_reporting_datasets",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Cree par",
            ),
        ),
        migrations.AddField(
            model_name="reportingdataset",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_reporting_datasets",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Modifie par",
            ),
        ),
        migrations.AddField(
            model_name="reportingvisualization",
            name="origin",
            field=models.CharField(
                choices=[("catalog", "Catalogue"), ("studio", "Studio")],
                default="catalog",
                max_length=20,
                verbose_name="Origine",
            ),
        ),
        migrations.AddField(
            model_name="reportingvisualization",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_reporting_visualizations",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Cree par",
            ),
        ),
        migrations.AddField(
            model_name="reportingvisualization",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_reporting_visualizations",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Modifie par",
            ),
        ),
        migrations.AddField(
            model_name="reportingreport",
            name="allowed_roles",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Roles autorises a consulter ce rapport.",
                verbose_name="Roles autorises",
            ),
        ),
        migrations.AddField(
            model_name="reportingreport",
            name="origin",
            field=models.CharField(
                choices=[("catalog", "Catalogue"), ("studio", "Studio")],
                default="catalog",
                max_length=20,
                verbose_name="Origine",
            ),
        ),
        migrations.AddField(
            model_name="reportingreport",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_reporting_reports",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Cree par",
            ),
        ),
        migrations.AddField(
            model_name="reportingreport",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_reporting_reports",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Modifie par",
            ),
        ),
        migrations.RunPython(copy_dataset_roles, migrations.RunPython.noop),
    ]
