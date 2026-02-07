from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import PasswordResetOTP, User, UserProfile, UserSettings


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    pass


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number", "birth_date")
    search_fields = ("user__username", "user__email", "phone_number")


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "theme", "mode", "layout")
    search_fields = ("user__username", "user__email")
    list_filter = ("theme", "mode", "layout")


@admin.register(PasswordResetOTP)
class PasswordResetOTPAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "expires_at", "is_used")
    search_fields = ("user__username", "user__email", "code")
    list_filter = ("is_used",)
