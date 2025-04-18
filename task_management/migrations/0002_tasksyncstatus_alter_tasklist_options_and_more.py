# Generated by Django 4.2.7 on 2025-03-27 16:28

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('task_management', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskSyncStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(choices=[('google', 'Google'), ('microsoft', 'Microsoft')], max_length=20)),
                ('is_complete', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AlterModelOptions(
            name='tasklist',
            options={'ordering': ['list_name']},
        ),
        migrations.RemoveField(
            model_name='tasklist',
            name='special_list',
        ),
        migrations.AddField(
            model_name='tasklist',
            name='list_source',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='tasklist',
            name='list_type',
            field=models.CharField(choices=[('special', 'Special'), ('google_primary', 'Google Primary'), ('microsoft_primary', 'Microsoft Primary'), ('normal', 'Normal')], default='normal', max_length=20),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['user', 'task_completed', 'due_date'], name='task_manage_user_id_06c0ac_idx'),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['source', 'source_id'], name='task_manage_source_13f0ef_idx'),
        ),
        migrations.AddField(
            model_name='tasksyncstatus',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterUniqueTogether(
            name='tasksyncstatus',
            unique_together={('user', 'provider')},
        ),
    ]
