from django.contrib.auth.hashers import identify_hasher, make_password
from django.db import migrations, models


def hash_backup_codes(apps, schema_editor):
    backup_code_model = apps.get_model("rail_django", "MFABackupCode")
    for backup_code in backup_code_model.objects.iterator():
        try:
            identify_hasher(backup_code.code)
        except ValueError:
            backup_code.code = make_password(backup_code.code)
            backup_code.save(update_fields=["code"])


class Migration(migrations.Migration):
    dependencies = [("rail_django", "0007_reporting_authoring_fields")]

    operations = [
        migrations.AlterField(
            model_name="mfabackupcode",
            name="code",
            field=models.CharField(max_length=128, verbose_name="Code de récupération"),
        ),
        migrations.RunPython(hash_backup_codes, migrations.RunPython.noop),
    ]
