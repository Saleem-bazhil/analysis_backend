"""
Management command to create the application users from environment variables.
Reads ADMIN_PASSWORD, SALEEM_PASSWORD, OPERATOR_PASSWORD from env.
Also reads <USERNAME>_REGION env vars for region-based RBAC.

Usage: python manage.py seed_users
"""

import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from api.models import UserProfile

User = get_user_model()

USERS = [
    {'username': 'admin', 'env_key': 'ADMIN_PASSWORD', 'is_staff': True, 'fallback': 'admin', 'region': ''},
    {'username': 'saleem', 'env_key': 'SALEEM_PASSWORD', 'is_staff': False, 'fallback': 'saleem123', 'region': 'Chennai'},
    {'username': 'operator', 'env_key': 'OPERATOR_PASSWORD', 'is_staff': False, 'fallback': 'operator123', 'region': 'Chennai'},
]


class Command(BaseCommand):
    help = 'Create or update application users from environment variables.'

    def handle(self, *args, **options):
        for user_cfg in USERS:
            username = user_cfg['username']
            password = os.environ.get(user_cfg['env_key'], user_cfg['fallback'])
            is_staff = user_cfg['is_staff']
            region = os.environ.get(f'{username.upper()}_REGION', user_cfg['region'])

            user, created = User.objects.get_or_create(
                username=username,
                defaults={'is_staff': is_staff},
            )

            # Always reset password to match env
            user.set_password(password)
            user.is_staff = is_staff
            user.save()

            # Create or update UserProfile with region
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.region = region
            profile.save()

            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(
                f'{action} user: {username} (region: {region or "All"})'
            ))
