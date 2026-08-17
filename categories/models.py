from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    """A grouping/tag used to classify events (e.g. Music, Tech, Sports)."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(max_length=300, blank=True)
    icon = models.CharField(
        max_length=50,
        default='bi-calendar-event',
        help_text="Bootstrap Icon class name, e.g. 'bi-music-note-beamed'."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='categories_created',
        help_text="Categories created before this field existed are left null "
                   "(Super Admin/Staff managed) rather than backfilled to a guess."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('categories:category_list')
