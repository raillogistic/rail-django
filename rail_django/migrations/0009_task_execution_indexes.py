from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rail_django", "0008_hash_mfa_backup_codes")]

    operations = [
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["owner_id", "-created_at"],
                name="rail_task_owner_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["status", "-created_at"],
                name="rail_task_status_created_idx",
            ),
        ),
    ]
