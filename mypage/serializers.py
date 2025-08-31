from rest_framework import serializers
from .models import AccountDeletionLog


class AccountDeletionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
    class Meta:
        model = AccountDeletionLog
        fields = ["id", "reason", "created_at", "user_id_snapshot", "user_name_snapshot", "account_id_snapshot"]