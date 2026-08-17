from django.db import models  # noqa: F401

# Module 8 deliberately has no models of its own. Every report is computed
# live from data already owned by another module (events, budget, tickets,
# vendors, staff, resources) — see reports/data.py. This avoids a second,
# possibly-stale copy of numbers that already live somewhere else, the same
# "derive it live" principle EventBudget uses for its own totals.
