from django.db import models
# Or for SQLite:
from django.db.models import JSONField

class Workflow(models.Model):
    name = models.CharField(max_length=255, unique=True)
    graph = JSONField()  # stores nodes, edges, tool parameters
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
