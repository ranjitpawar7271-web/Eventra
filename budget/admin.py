from django.contrib import admin

from .models import EventBudget, Expense, RevenueEntry


@admin.register(EventBudget)
class EventBudgetAdmin(admin.ModelAdmin):
    list_display = ('event', 'estimated_budget', 'total_expenses', 'total_revenue', 'profit_or_loss')
    search_fields = ('event__title',)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('description', 'budget', 'category', 'amount', 'status', 'date')
    list_filter = ('category', 'status')
    search_fields = ('description', 'budget__event__title')


@admin.register(RevenueEntry)
class RevenueEntryAdmin(admin.ModelAdmin):
    list_display = ('budget', 'source', 'amount', 'date')
    list_filter = ('source',)
    search_fields = ('budget__event__title', 'sponsor_name')
