from django.contrib import admin
from .models import AccountDeletionLog


class AccountDeletionLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id_snapshot", "user_name_snapshot", "account_id_snapshot", "reason", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user_name_snapshot", "account_id_snapshot", "reason")
    ordering = ("-created_at",)


admin.site.register(AccountDeletionLog, AccountDeletionLogAdmin)
