from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from rail_django.core.meta import GraphQLMeta as GraphQLMetaBase

from .access_control import (
    USER_ROLES,
    profile_operations,
    settings_operations,
    user_operations,
)


class User(AbstractUser):
    """Custom project user model."""

    def __str__(self) -> str:
        return self.username

    @property
    def desc(self) -> str:
        return self.username

    class GraphQLMeta(GraphQLMetaBase):
        access = GraphQLMetaBase.AccessControl(
            roles=USER_ROLES,
            operations=user_operations(),
        )


class UserProfile(models.Model):
    """Optional profile data attached to a user."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(blank=True, help_text="User biography")
    birth_date = models.DateField(null=True, blank=True, help_text="User birth date")
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="User phone number",
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    class GraphQLMeta(GraphQLMetaBase):
        access = GraphQLMetaBase.AccessControl(
            roles=USER_ROLES,
            operations=profile_operations(),
        )

    def __str__(self) -> str:
        return f"Profile for {self.user.username}"


class UserSettings(models.Model):
    """Simple frontend preferences attached to a user."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    theme = models.CharField(max_length=50, default="default", help_text="UI Theme")
    mode = models.CharField(max_length=20, default="light", help_text="UI Mode (light/dark)")
    layout = models.CharField(max_length=20, default="vertical", help_text="UI Layout")
    sidebar_collapse_mode = models.CharField(
        max_length=20,
        default="offcanvas",
        help_text="Sidebar collapse mode",
    )
    font_size = models.CharField(max_length=10, default="md", help_text="Font size")
    font_family = models.CharField(max_length=50, default="inter", help_text="Font family")

    class Meta:
        verbose_name = "User Settings"
        verbose_name_plural = "User Settings"

    class GraphQLMeta(GraphQLMetaBase):
        access = GraphQLMetaBase.AccessControl(
            roles=USER_ROLES,
            operations=settings_operations(),
        )

    def __str__(self) -> str:
        return f"Settings for {self.user.username}"


class PasswordResetOTP(models.Model):
    """One-time code for password reset flows."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_codes")
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()

    def __str__(self):
        return f"Reset code for {self.user.username}"
