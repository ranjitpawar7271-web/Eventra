from decimal import Decimal

from django.db import models


class Currency(models.Model):
    """A currency and its conversion rate against the platform's base
    currency (INR — every existing price/budget/revenue field in this
    project is already stored and computed in INR).

    Scope, deliberately: this is a **display-only conversion layer**, not
    a rewrite of how money is stored. `EventBudget.total_revenue`,
    `sys_total_revenue` on the dashboard, ticket prices, sponsorship
    amounts — all of that continues to store and sum in INR exactly as
    before, completely untouched by this feature. What changes is only
    how a price is *shown* to someone who picked a different display
    currency: it's converted on the fly using this manually-maintained
    rate, per the module plan's own note that live FX rates would need
    an external API dependency this project doesn't have. Retrofitting
    genuine multi-currency ledgers (multiple currencies actually stored
    and reconciled) into budget/tickets/sponsors would be a much larger,
    riskier change touching a lot of already-tested financial code for a
    feature that was scoped as a currency *field* + conversion table.
    """

    code = models.CharField(max_length=3, unique=True, help_text="ISO 4217 code, e.g. USD, EUR, INR.")
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=5)
    rate_to_base = models.DecimalField(
        max_digits=12, decimal_places=6, default=Decimal('1.000000'),
        help_text="How many units of this currency equal 1 unit of the base currency (INR)."
    )
    is_base = models.BooleanField(
        default=False,
        help_text="Exactly one currency should be marked base — this project's base is INR."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name_plural = 'currencies'

    def __str__(self):
        return f"{self.code} ({self.symbol})"

    def convert_from_base(self, base_amount):
        """Converts an INR amount into this currency using the stored
        rate. Never raises on bad input types — a display helper should
        degrade gracefully, not 500 a page over a price field."""
        try:
            amount = Decimal(str(base_amount))
        except Exception:
            amount = Decimal('0')
        return (amount * self.rate_to_base).quantize(Decimal('0.01'))

    @classmethod
    def get_base(cls):
        return cls.objects.filter(is_base=True).first()
