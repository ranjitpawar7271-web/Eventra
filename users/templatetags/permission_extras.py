from django import template

from users.permissions import can_manage_catalog_item

register = template.Library()


@register.filter
def can_manage(obj, user):
    """Usage: {% if category|can_manage:user %} ... {% endif %}

    Thin template wrapper around users.permissions.can_manage_catalog_item
    so templates can show/hide Edit/Delete controls per-object instead of
    an all-or-nothing role check. This is a UI convenience only — every
    view already re-checks the same permission server-side, since a
    hidden button is never a substitute for backend authorization.
    """
    if obj is None or user is None:
        return False
    return can_manage_catalog_item(user, obj)
