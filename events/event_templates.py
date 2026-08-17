"""'Event Templates' (Module 10): pre-filled Event creation presets for
common event types. Deliberately a plain dict, not a database model —
the spec asks for "pre-filled Event creation presets," which is exactly
what Django's `Form(initial=...)` already does. A model + CRUD screens
for something that's really five hardcoded starting points would be
more machinery than the feature needs; if organizers ever want to save
their *own* custom templates, that's a different, larger feature
("save this event as a template") worth its own decision, not something
to bolt on silently here.
"""

EVENT_TEMPLATES = {
    'conference': {
        'label': 'Conference',
        'icon': 'bi-mic',
        'title': 'Annual Conference',
        'description': (
            "Join us for a day of keynote talks, breakout sessions, and networking.\n\n"
            "Agenda:\n- Opening keynote\n- Breakout sessions\n- Panel discussion\n- Closing remarks & networking"
        ),
        'capacity': 200,
        'price': 500,
    },
    'wedding': {
        'label': 'Wedding',
        'icon': 'bi-heart',
        'title': "[Names]'s Wedding Celebration",
        'description': (
            "We're delighted to invite you to celebrate our special day with us.\n\n"
            "Please join us for the ceremony followed by dinner and dancing."
        ),
        'capacity': 100,
        'price': 0,
    },
    'seminar': {
        'label': 'Seminar',
        'icon': 'bi-easel',
        'title': 'Seminar: [Topic]',
        'description': (
            "A focused session covering [topic], led by an expert speaker.\n\n"
            "Includes a Q&A session at the end."
        ),
        'capacity': 60,
        'price': 0,
    },
    'workshop': {
        'label': 'Workshop',
        'icon': 'bi-tools',
        'title': 'Hands-on Workshop: [Skill]',
        'description': (
            "A hands-on, small-group workshop where you'll learn [skill] by doing.\n\n"
            "Please bring a laptop. All materials provided."
        ),
        'capacity': 30,
        'price': 750,
    },
    'hackathon': {
        'label': 'Hackathon',
        'icon': 'bi-code-slash',
        'title': '[Theme] Hackathon',
        'description': (
            "A 24-hour hackathon — build something original around this year's theme.\n\n"
            "Schedule:\n- Kickoff & team formation\n- Building time\n- Submissions close\n- Judging & prizes"
        ),
        'capacity': 120,
        'price': 0,
    },
}


def get_template_initial(template_key):
    """Returns the Form(initial=...) dict for a template key, or None if
    the key doesn't match a known template (including a blank/missing
    query param) — the view falls back to a normal blank form either
    way."""
    template = EVENT_TEMPLATES.get(template_key)
    if not template:
        return None
    return {
        'title': template['title'],
        'description': template['description'],
        'capacity': template['capacity'],
        'price': template['price'],
    }
