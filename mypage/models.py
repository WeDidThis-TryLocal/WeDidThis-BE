from django.db import models
from django.db.models import SET_NULL
from django.conf import settings

from accounts.models import User


class AccountDeletionLog(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=SET_NULL, related_name="deletion_logs")

    # 스냅샷
    user_id_snapshot = models.IntegerField(null=True, blank=True)
    user_name_snapshot = models.CharField(max_length=50, null=True, blank=True)
    account_id_snapshot = models.CharField(max_length=30, null=True, blank=True)

    reason = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[탈퇴] {self.user_name_snapshot or self.user_id_snapshot} - {self.reason}"