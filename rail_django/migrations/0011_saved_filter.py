from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('rail_django', '0010_task_execution'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SavedFilter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('model_name', models.CharField(help_text="The GraphQL type/model name this filter applies to (e.g. 'Order')", max_length=100)),
                ('filter_json', models.JSONField(help_text='The JSON representation of the where clause')),
                ('description', models.TextField(blank=True)),
                ('is_shared', models.BooleanField(default=False, help_text='If true, other users can see and use this filter')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('use_count', models.PositiveIntegerField(default=0)),
                ('created_by', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='saved_filters', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
                'unique_together': {('name', 'created_by', 'model_name')},
            },
        ),
    ]
