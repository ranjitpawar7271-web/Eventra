from django import forms

from .models import Ticket


class TicketTypeForm(forms.ModelForm):
    """Lets an event manager upgrade/correct a ticket's type (e.g. Free -> VIP)."""

    class Meta:
        model = Ticket
        fields = ('ticket_type',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ticket_type'].widget.attrs.update({'class': 'form-select form-select-sm'})


class TicketStatusForm(forms.ModelForm):
    """Manual override for cancel/refund. Checked-in tickets go through the
    scanner, not this form — see the guard in views.ticket_status_update."""

    class Meta:
        model = Ticket
        fields = ('status',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].choices = [
            (Ticket.STATUS_ISSUED, 'Issued'),
            (Ticket.STATUS_CANCELLED, 'Cancelled'),
            (Ticket.STATUS_REFUNDED, 'Refunded'),
        ]
        self.fields['status'].widget.attrs.update({'class': 'form-select form-select-sm'})
