from django.db import models


class Language(models.TextChoices):
    ENGLISH = "en", "English"
    KINYARWANDA = "rw", "Kinyarwanda"
