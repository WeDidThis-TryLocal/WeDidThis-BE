from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import *


PROTECTED_ROUTE_IDS = {1, 2, 3, 4, 5}
UNPROTECTED_ROUTE_NAME = "나의 여정"
@receiver(post_delete, sender=QuestionnaireSubmission)
def delete_orphaned_route(sender, instance, **kwargs):
    route = instance.route
    if not route:
        return
    
    if route.submissions.exists():
        return
    
    if route.id in PROTECTED_ROUTE_IDS:
        return
    
    if route.name != UNPROTECTED_ROUTE_NAME:
        return
    
    route.delete()