from django.conf import settings
from django.db import migrations


def create_profiles_for_existing_users(apps, schema_editor):
    Profile = apps.get_model('blog', 'Profile')
    User = apps.get_model(settings.AUTH_USER_MODEL.split('.')[0], settings.AUTH_USER_MODEL.split('.')[1])
    Profile.objects.bulk_create(
        [Profile(user_id=user.pk) for user in User.objects.all()],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('blog', '0006_profile'),
    ]

    operations = [migrations.RunPython(create_profiles_for_existing_users, migrations.RunPython.noop)]
