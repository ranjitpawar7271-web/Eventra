"""
Seed the database with realistic demo data for local development / demos.

Usage:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --flush   # wipe previously-seeded demo data first

Safe to re-run: uses get_or_create()/unique demo usernames so running it
twice does not create duplicates.

All demo users share the password:  demo1234
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

DEMO_PASSWORD = 'demo1234'


class Command(BaseCommand):
    help = "Seed the database with demo users, events, venues, tasks, etc."

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help="Delete previously-seeded demo users (and their related data) before seeding.",
        )

    def handle(self, *args, **options):
        from budget.models import EventBudget, Expense, RevenueEntry
        from categories.models import Category
        from events.models import Event, Registration
        from staff.models import Department, ShiftAssignment, StaffProfile
        from tasks.models import Task
        from users.models import User
        from vendors.models import VendorProfile
        from venues.models import Venue

        if options['flush']:
            self._flush(User)

        with transaction.atomic():
            users = self._create_users(User)
            categories = self._create_categories(Category, users['admin'])
            venues = self._create_venues(Venue, users['admin'])
            events = self._create_events(Event, categories, venues, users)
            self._create_registrations(Registration, events, users)
            self._create_staff(Department, StaffProfile, ShiftAssignment, users, events)
            self._create_vendor(VendorProfile, users)
            self._create_tasks(Task, events, users)
            self._create_budgets(EventBudget, Expense, RevenueEntry, events, users)

        self.stdout.write(self.style.SUCCESS(
            "\nDemo data seeded successfully.\n"
            f"All demo accounts use the password: {DEMO_PASSWORD}\n"
            "Usernames: demo_admin, demo_organizer1, demo_organizer2, "
            "demo_participant1..5, demo_staff, demo_vendor"
        ))

    # ------------------------------------------------------------------

    def _flush(self, User):
        deleted, _ = User.objects.filter(username__startswith='demo_').delete()
        self.stdout.write(self.style.WARNING(f"Flushed {deleted} demo-related rows."))

    def _create_users(self, User):
        specs = [
            ('demo_admin', User.SUPER_ADMIN, 'Asha', 'Rao', True, True),
            ('demo_organizer1', User.ORGANIZER, 'Rahul', 'Mehta', False, False),
            ('demo_organizer2', User.ORGANIZER, 'Priya', 'Nair', False, False),
            ('demo_staff', User.STAFF, 'Karan', 'Singh', True, False),
            ('demo_vendor', User.VENDOR, 'Vendor', 'Co', False, False),
            ('demo_participant1', User.PARTICIPANT, 'Aditi', 'Sharma', False, False),
            ('demo_participant2', User.PARTICIPANT, 'Vikram', 'Patel', False, False),
            ('demo_participant3', User.PARTICIPANT, 'Neha', 'Gupta', False, False),
            ('demo_participant4', User.PARTICIPANT, 'Rohan', 'Verma', False, False),
            ('demo_participant5', User.PARTICIPANT, 'Sneha', 'Joshi', False, False),
        ]

        users = {}
        for username, role, first, last, is_staff_flag, is_superuser in specs:
            user, created = User.objects.get_or_create(
                username=username,
                defaults=dict(
                    email=f'{username}@example.com',
                    first_name=first,
                    last_name=last,
                    role=role,
                    is_staff=is_staff_flag,
                    is_superuser=is_superuser,
                ),
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            key = {
                'demo_admin': 'admin',
                'demo_organizer1': 'organizer1',
                'demo_organizer2': 'organizer2',
                'demo_staff': 'staff',
                'demo_vendor': 'vendor',
                'demo_participant1': 'participant1',
                'demo_participant2': 'participant2',
                'demo_participant3': 'participant3',
                'demo_participant4': 'participant4',
                'demo_participant5': 'participant5',
            }[username]
            users[key] = user

        self.stdout.write(self.style.SUCCESS(f"Users ready: {len(users)}"))
        return users

    def _create_categories(self, Category, admin):
        names = ['Music', 'Technology', 'Sports', 'Food & Drink', 'Business', 'Arts & Culture']
        cats = {}
        for name in names:
            cat, _ = Category.objects.get_or_create(
                name=name,
                defaults=dict(created_by=admin, slug=slugify(name)),
            )
            cats[name] = cat
        self.stdout.write(self.style.SUCCESS(f"Categories ready: {len(cats)}"))
        return cats

    def _create_venues(self, Venue, admin):
        specs = [
            ('Grand Convention Hall', 'MG Road', 'Pune', 500),
            ('Riverside Amphitheatre', 'Riverside Ave', 'Pune', 1200),
            ('Skyline Rooftop', 'Baner Road', 'Pune', 150),
        ]
        venues = {}
        for name, address, city, capacity in specs:
            venue, _ = Venue.objects.get_or_create(
                name=name,
                defaults=dict(
                    slug=slugify(name),
                    address=address,
                    city=city,
                    capacity=capacity,
                    created_by=admin,
                ),
            )
            venues[name] = venue
        self.stdout.write(self.style.SUCCESS(f"Venues ready: {len(venues)}"))
        return venues

    def _create_events(self, Event, categories, venues, users):
        now = timezone.now()
        venue_list = list(venues.values())
        specs = [
            ('Indie Music Night', 'Music', 0, 'published', -5),
            ('AI & Cloud Summit 2026', 'Technology', 1, 'published', 3),
            ('City Marathon', 'Sports', 2, 'published', 10),
            ('Startup Founders Meetup', 'Business', 0, 'published', 20),
            ('Food Truck Festival', 'Food & Drink', 1, 'published', 30),
            ('Contemporary Art Expo', 'Arts & Culture', 2, 'draft', 45),
        ]
        organizers = [users['organizer1'], users['organizer2']]
        events = {}
        for i, (title, cat_name, venue_idx, status, day_offset) in enumerate(specs):
            organizer = organizers[i % len(organizers)]
            start = now + timedelta(days=day_offset, hours=2)
            end = start + timedelta(hours=3)
            event, _ = Event.objects.get_or_create(
                title=title,
                defaults=dict(
                    slug=slugify(title),
                    description=f"Demo event: {title}. Seeded for local development.",
                    category=categories[cat_name],
                    organizer=organizer,
                    location=venue_list[venue_idx].name,
                    venue=venue_list[venue_idx],
                    start_date=start,
                    end_date=end,
                    capacity=100,
                    price=0 if 'Meetup' in title else 499,
                    status=status,
                ),
            )
            events[title] = event

        self._auto_approve_held_back_events(events, users, intended_published={
            title for title, _, _, status, _ in specs if status == 'published'
        })

        self.stdout.write(self.style.SUCCESS(f"Events ready: {len(events)}"))
        return events

    def _auto_approve_held_back_events(self, events, users, intended_published):
        """If this project's WorkflowSettings has `require_event_approval`
        turned on, the publish-gate signal will have quietly held any of
        the events above back as Draft (see workflow/signals.py). Push
        them through the real approval flow so the demo data ends up in
        the state it was seeded to represent, instead of silently
        leaving 'published' events stuck as drafts.
        """
        from django.contrib.contenttypes.models import ContentType

        from workflow.models import ApprovalStep

        approved_count = 0
        for title in intended_published:
            event = events[title]
            if event.status == 'published':
                continue

            step = ApprovalStep.objects.filter(
                content_type=ContentType.objects.get_for_model(event.__class__),
                object_id=event.pk,
                stage=ApprovalStep.STAGE_PUBLISHED,
                status=ApprovalStep.STATUS_PENDING,
            ).first()

            if step:
                step.approve(users['admin'], comment='Auto-approved by seed_demo_data.')
                event.refresh_from_db()
                approved_count += 1

        if approved_count:
            self.stdout.write(self.style.WARNING(
                f"Auto-approved {approved_count} demo event(s) held back by the "
                "'require approval to publish' workflow setting."
            ))

    def _create_registrations(self, Registration, events, users):
        published = [e for e in events.values() if e.status == 'published']
        participants = [users[f'participant{i}'] for i in range(1, 6)]
        count = 0
        for i, event in enumerate(published):
            for participant in participants[: (i % len(participants)) + 2]:
                _, created = Registration.objects.get_or_create(
                    event=event, user=participant,
                    defaults=dict(status='confirmed'),
                )
                count += created
        self.stdout.write(self.style.SUCCESS(f"Registrations created: {count}"))

    def _create_staff(self, Department, StaffProfile, ShiftAssignment, users, events):
        dept, _ = Department.objects.get_or_create(name='Operations')
        profile, created = StaffProfile.objects.get_or_create(
            user=users['staff'],
            defaults=dict(employee_id='EMP-DEMO-1', department=dept, designation='Event Coordinator'),
        )
        upcoming = [e for e in events.values() if e.start_date > timezone.now()]
        if upcoming:
            event = upcoming[0]
            ShiftAssignment.objects.get_or_create(
                staff=profile, title='Registration Desk', event=event,
                start_datetime=event.start_date - timedelta(hours=1),
                end_datetime=event.start_date + timedelta(hours=1),
                defaults=dict(status='assigned', assigned_by=users['admin']),
            )
        self.stdout.write(self.style.SUCCESS("Staff profile + shift ready"))

    def _create_vendor(self, VendorProfile, users):
        VendorProfile.objects.get_or_create(
            user=users['vendor'],
            defaults=dict(company_name='Demo Catering Co.'),
        )
        self.stdout.write(self.style.SUCCESS("Vendor profile ready"))

    def _create_tasks(self, Task, events, users):
        count = 0
        for event in list(events.values())[:3]:
            for title, offset in [('Book catering', -2), ('Confirm AV setup', -1), ('Send reminder emails', 0)]:
                _, created = Task.objects.get_or_create(
                    event=event, title=title,
                    defaults=dict(
                        due_date=(event.start_date + timedelta(days=offset)).date(),
                        assigned_to=event.organizer,
                    ),
                )
                count += created
        self.stdout.write(self.style.SUCCESS(f"Tasks created: {count}"))

    def _create_budgets(self, EventBudget, Expense, RevenueEntry, events, users):
        """One EventBudget per demo event, with a handful of Expense line
        items (mixed statuses, so 'pending' vs 'approved/paid' behaves
        realistically) and a manual RevenueEntry, so the Budget module's
        totals/variance/profit views have something real to show.
        """
        expense_plan = [
            ('venue', 'Venue deposit', 8000, -10, 'paid'),
            ('catering', 'Catering advance', 5000, -7, 'approved'),
            ('marketing', 'Social media ads', 1500, -5, 'approved'),
            ('equipment', 'Sound & lighting rental', 3000, -3, 'pending'),
        ]

        budget_count = 0
        expense_count = 0
        revenue_count = 0

        for event in events.values():
            budget, created = EventBudget.objects.get_or_create(
                event=event,
                defaults=dict(
                    estimated_budget=20000,
                    created_by=users['admin'],
                ),
            )
            budget_count += created

            event_date = event.start_date.date()

            for category, description, amount, day_offset, status in expense_plan:
                _, created = Expense.objects.get_or_create(
                    budget=budget, description=description,
                    defaults=dict(
                        category=category,
                        amount=amount,
                        date=event_date + timedelta(days=day_offset),
                        status=status,
                        recorded_by=event.organizer,
                    ),
                )
                expense_count += created

            _, created = RevenueEntry.objects.get_or_create(
                budget=budget, source='sponsorship', sponsor_name='Demo Sponsor Co.',
                defaults=dict(
                    description='Local sponsor contribution',
                    amount=6000,
                    date=event_date - timedelta(days=8),
                    recorded_by=event.organizer,
                ),
            )
            revenue_count += created

        self.stdout.write(self.style.SUCCESS(
            f"Budgets ready: {budget_count} created, "
            f"{expense_count} expenses, {revenue_count} revenue entries"
        ))