# Eventra — Smart Event Planning Platform with Resource coordination system

Your original spec describes a full enterprise SaaS platform. Building all of
it in one pass isn't realistic to do at production quality, so it's being
built **module by module**, per your own instructions — each module fully
functional, tested, and integrated before the next one starts.

## ✅ Module 1 — Role-Based Authentication (DONE, this delivery)

**What changed:**
- `users/models.py` — added `role` field (`super_admin`, `organizer`,
  `staff`, `vendor`, `volunteer`, `participant`). The old `is_organizer`
  flag still exists and is kept in sync automatically, so nothing that
  read it before is broken.
- `users/permissions.py` (new) — `role_required(*roles)` decorator and
  `RoleRequiredMixin` for class-based views. Every future module reuses
  this instead of re-implementing access checks.
- `users/forms.py` — sign-up now lets people choose Organizer / Vendor /
  Volunteer / Participant. **Super Admin and Staff are not
  self-selectable** — they're granted via Django admin (`/admin/`) or a
  future "Manage Users" screen. This is a deliberate security choice.
- `events/views.py` — event creation now requires `can_manage_events`
  (Organizer, Staff, or Super Admin) instead of "any logged-in user
  becomes an organizer the moment they click Create." **This is an
  intentional behavior change** consistent with your spec's role
  permission model — flagging it explicitly since your project
  previously allowed anyone to create events.
- `dashboard/views.py` + `dashboard/dashboard.html` — Super Admins now
  see a system-wide panel: total/active/upcoming/completed/cancelled
  events, and user counts by role. All numbers come from your real data,
  nothing is faked.
- `users/migrations/0002_user_role.py` — adds the field and **backfills
  existing users**: anyone with `is_organizer=True` becomes `role=organizer`
  automatically. Applied and verified against your actual `db.sqlite3`.
- `users/tests.py` — 11 tests covering role defaults, the legacy sync
  logic (this caught and fixed a real bug where `save(update_fields=...)`
  could silently drop the role change), sign-up restrictions, event
  permission enforcement, and dashboard branching. All passing.

**Verified:** migration applied to your real database without data loss,
full test suite green, and manual smoke tests of login/signup/profile/
dashboard/event-create across Participant, Organizer, and Super Admin
roles all returned correct responses.

**Not yet built (still using the built-in Django admin for now):** a
dedicated in-app "Manage Users" screen to assign Staff/Super Admin roles
without touching `/admin/`. That's a natural fit for Module 5 (Staff
Management) rather than bolting it in here.

## ✅ Module 2 — Venue Management (DONE, this delivery)

**What's new:**
- New `venues` app: `Venue`, `VenueBooking`, `MaintenanceSchedule` models.
- Venues have name, address, city, capacity, comma-separated facilities,
  description, image, active/inactive flag.
- **Conflict detection is enforced at the model layer** (`Venue.is_available()`,
  used by both `VenueBooking.clean()` and `MaintenanceSchedule.clean()`), so
  it can't be bypassed by calling `.objects.create()` directly, from the
  admin, from a form, or from a future API — double-booking a venue, or
  booking it during scheduled maintenance, is rejected wherever it's
  attempted.
- **Availability calendar** — a month-view calendar per venue
  (`/venues/<slug>/calendar/`) showing booked vs. open days, with
  prev/next month navigation, plus lists of that month's bookings and
  maintenance windows with cancel/remove actions.
- **Maintenance scheduling** — Staff/Super Admin can block a venue off;
  this is checked the same way as a booking, so maintenance can't be
  scheduled over an existing confirmed booking (and vice versa).
- **Event integration** — `Event` gained an optional `venue` FK
  alongside the existing free-text `location` field (nothing removed,
  fully backward compatible — events without a registered venue keep
  working exactly as before). When an organizer picks a venue for their
  event:
  - a `VenueBooking` is created/kept in sync automatically,
  - the event's date range is checked against that venue's other
    bookings and maintenance windows,
  - the event's capacity is checked against the venue's capacity,
  - all before the event is saved, with a clear form error if there's a conflict.
- Role permissions (reusing Module 1's `role_required`): **Staff/Super
  Admin manage the venue catalog** (create/edit/delete venues, schedule
  maintenance); **any authenticated user with venue access can book** an
  existing venue; **anyone can browse** venues (public listing + detail,
  same as events).
- `venues/migrations/0001_initial.py` and `events/migrations/0003_event_venue.py`
  — both hand-verified against your real `db.sqlite3` (0 changes reported
  by `makemigrations --check`, applied cleanly, all 7 existing events and
  both users intact afterward).
- `venues/tests.py` — 14 tests: slug generation, availability logic
  (overlap, back-to-back non-overlap, cancelled bookings don't block,
  maintenance blocking), conflict rejection at the model layer, role
  permissions on venue management, and full event↔venue integration
  (booking sync, conflict rejection, capacity validation) via real HTTP
  requests. Combined with Module 1, **25/25 tests pass**.
- Also smoke-tested manually end-to-end: venue create → detail → calendar
  → event creation with that venue → booking sync verified → a second,
  conflicting booking attempt correctly rejected.

**Not built yet (intentionally deferred):** venue image galleries (multiple
photos per venue — spec says "Images" plural; shipped with one primary
image for now, gallery is a small add-on for later if you want it), and
a "book a venue directly from the calendar" shortcut (currently: Book Now
button + separate calendar view). Neither blocks anything downstream.

## ✅ Module 3 — Resource Management (DONE, this delivery)

**What's new:**
- New `resources` app: `Resource`, `ResourceAllocation`, `DamageReport` models.
- Resources are **quantity-based pools**, not single exclusive items like
  Venues — a Resource is "100 plastic chairs" and allocations draw a
  quantity from that pool for a time window, rather than reserving the
  whole thing. Categories cover everything the spec listed: Chairs,
  Tables, Projectors, Sound Systems, Lights, Vehicles, Generators,
  Decoration Items, plus Other.
- **"Automatically prevent double allocation" is enforced at the model
  layer** (`Resource.available_quantity()` / `is_available()`, used by
  `ResourceAllocation.clean()`): the sum of everything already allocated
  for an overlapping time window is subtracted from usable inventory, and
  any request that would push it negative is rejected — whether it comes
  through the form, the admin, or a future API. Verified with a real
  scenario: 100 chairs, 70 allocated, a second request for 40 overlapping
  the same window is correctly rejected; two 30-chair requests for
  overlapping windows both succeed (100 ≥ 60).
- **Damage reports pull inventory out of the usable pool automatically.**
  `Resource.usable_quantity` = total − sum of damage reports still
  "reported" or "under repair". Marking a report resolved returns those
  units to the pool immediately — confirmed end-to-end (50 → 40 after a
  10-unit damage report, back to 50 after resolving it).
- **Return workflow** — allocations can be marked returned (freeing the
  quantity immediately) or cancelled, by the person who requested them or
  by Staff/Super Admin.
- Optional link to `Event`, same pattern as venues — an allocation can
  (but doesn't have to) be tied to the event it's for.
- Role permissions (reusing Module 1's `role_required`): **Staff/Super
  Admin manage the resource catalog** (add/edit/delete resources, resolve
  damage reports); **Organizer/Staff/Super Admin can request
  allocations** (Vendors/Volunteers/Participants can't — verified a
  Vendor gets redirected); **anyone can browse** the resource catalog
  publicly, same as events/venues.
- `resources/migrations/0001_initial.py` — hand-verified against your
  real `db.sqlite3` (0 changes reported by `makemigrations --check`,
  applied cleanly, all users/events/venues intact afterward).
- `resources/tests.py` — 16 tests covering the allocation pool math
  (availability, double-allocation rejection, multiple valid overlapping
  allocations, cancellation/return freeing the pool), damage report
  math (usable-quantity reduction and restoration, rejecting damage
  claims larger than total inventory), role permissions, and the full
  allocation request flow through real HTTP requests. Combined with
  Modules 1–2, **42/42 tests pass.**
- Also smoke-tested manually end-to-end through the real views: resource
  create → allocate 30/50 → attempt to over-allocate (correctly
  rejected) → file a damage report → confirm pool shrinks → return the
  allocation and resolve the damage report → confirm pool is back to
  full. One thing worth knowing while testing this yourself: the app's
  `TIME_ZONE` is `Asia/Kolkata`, so times typed into the datetime-local
  inputs are interpreted as IST, same as any real user filling out the
  form in their browser — my first pass at a smoke-test script built
  timestamps from raw UTC without localizing and got a false negative
  for a second, until I fixed the script (not the app) to match how a
  browser actually submits local time.

**Not built yet (intentionally deferred):** a resource "availability
calendar" like the venue one — resources are pooled/quantity-based
rather than single-slot, so a day-by-day calendar is less informative
than for venues; a small quantity-over-time chart would fit better and
is a natural pairing with Module 8 (Reports & Analytics) rather than
being bolted on here.

## ✅ Module 4 — Vendor Management (DONE, this delivery)

**What's new:**
- New `vendors` app: `VendorProfile`, `VendorService`, `VendorDocument`,
  `VendorContract`, `VendorRating`, `VendorPayment` models.
- **Registration** — anyone who signed up with the Vendor role (from
  Module 1) can register a `VendorProfile` (one per account). It starts
  `pending` and is **not shown in the public directory** until Staff or
  Super Admin approves it — verified: a pending vendor is invisible to
  an anonymous request but visible to Staff and to the vendor themself.
  Approve/reject/suspend actions are logged against the reviewing admin.
- **Services** — vendors list what they offer with pricing (flat / per
  hour / per day / per person / per event); only the vendor who owns the
  profile (or Staff/Super Admin) can add or remove services — verified
  an organizer cannot add a service to someone else's vendor listing.
- **Documents** — generic upload for licenses, certifications, insurance
  proof, contracts, with the same owner-or-admin permission check.
- **Contracts** — Organizer/Staff/Super Admin can open a contract with a
  vendor, optionally tied to one of their own events, with an amount,
  dates, and an optional uploaded document; status moves through
  draft → sent → signed → completed/cancelled. Verified a Participant is
  blocked from creating a contract, an Organizer can.
- **Payments** — Staff/Super Admin record payments against a contract
  (bank transfer / UPI / cheque / cash), and `VendorContract.total_paid`
  / `balance_due` are computed live from confirmed (`status='paid'`)
  payments only — a `pending` payment doesn't count toward the balance
  until it's actually marked paid. Verified: ₹20,000 contract, ₹8,000
  paid → balance correctly shows ₹12,000.
- **Ratings & Performance Score** — Organizer/Staff/Super Admin rate a
  vendor's Service Quality and Delivery Time (1–5 each) after working
  with them; `VendorProfile.performance_score` is the live average of
  both across all ratings. Verified with two ratings (4/2 and 5/3):
  quality avg 4.5, delivery avg 2.5, performance score 3.5 — matches
  hand-calculated expectation exactly, and the smoke test's own
  independent scenario (5/4 → 4.5) also checked out.
- `vendors/migrations/0001_initial.py` — hand-verified against your real
  `db.sqlite3` (0 changes reported by `makemigrations --check`, applied
  cleanly, all users/events/venues/resources intact afterward).
- `vendors/tests.py` — 19 tests covering slug generation, approval-gated
  visibility, performance score math, contract balance math (including
  that pending payments don't count), date validation, and the full
  permission matrix (who can register, approve, add services, create
  contracts). Combined with Modules 1–3, **61/61 tests pass.**
- Also smoke-tested manually end-to-end through the real views: vendor
  registers → hidden from public list → staff approves → now public →
  vendor adds a service → organizer opens a contract → staff records a
  partial payment → organizer rates the vendor → vendor's own attempt to
  self-approve is correctly blocked.

**Not built yet (intentionally deferred):** vendor-side contract
e-signing (currently: Staff/Admin/Organizer move status to "signed"
manually — a vendor-facing "I agree" flow that also writes `signed_at`
is a small add-on for later, not required for the module to function);
automated payment reminders (fits naturally with Module 9 — Workflow &
Notifications — rather than being bolted on here).

## ✅ Module 5 — Staff Management (DONE, this delivery)

**What's new:**
- New `staff` app: `Department`, `StaffProfile`, `ShiftAssignment`,
  `AttendanceRecord`, `SalaryRecord` models.
- **In-app staff onboarding** — Super Admin looks up an existing user by
  username and "onboards" them: creates their HR profile (employee ID,
  department, designation, skills) and promotes their `role` to Staff in
  the same action. This replaces the Django-admin-only role assignment
  flagged back in Module 1's roadmap — verified end-to-end: a plain
  Participant account is promoted to `role=staff` and gets a
  `StaffProfile` in one form submission.
- **"Assign staff automatically based on availability"** (a literal spec
  requirement) — `StaffProfile.find_available()` filters active staff by
  department/skill and excludes anyone with a conflicting shift; the
  Auto-Assign screen takes a time window plus those optional filters and
  assigns the first match in one action. Verified: two staff in the same
  department, one already busy — auto-assign correctly skips the busy
  one and picks the free one matching the requested skill.
- **Double-booking prevention for people** — same conflict-detection
  pattern as venues/resources: `ShiftAssignment.clean()` rejects any new
  shift that overlaps another `assigned` shift for that staff member.
  Verified: a second, overlapping shift assignment for the same person
  is correctly rejected via the form.
- **Attendance** — self-service check-in/out for staff, with Super Admin
  able to record on anyone's behalf. Verified a staff member can mark
  their own attendance but is blocked from marking someone else's.
- **Salary records** — Super-Admin-only to create; `net_amount` is a
  computed property (`basic + bonus − deductions`). **Confidentiality
  verified**: an Organizer viewing another staff member's profile page
  never sees their salary figures in the rendered HTML, while the staff
  member viewing their own profile does.

**A real bug found and fixed while testing this module — and traced back
across Modules 2–4 too:** several "who did this" audit fields (like
`created_by`, `recorded_by`, `assigned_by`) were declared `null=True`
(correct — allows the field to go empty if that user account is later
deleted) but were missing `blank=True`, so Django's validation treated
them as *required input* rather than *optional/system-set*. This surfaced
as real failures: onboarding a staff member without picking a department
failed, and creating a shift/salary record without explicitly passing the
recording user failed model validation. Since this is the same field
pattern used in Modules 2, 3, and 4, I checked all of them and found the
identical issue in `Venue`/`MaintenanceSchedule` (Module 2),
`Resource`/`DamageReport` (Module 3), and
`VendorDocument`/`VendorContract`/`VendorRating`/`VendorPayment` (Module
4) — none of it was caught earlier because every existing test and view
always supplied those fields, so the missing `blank=True` was silent
until Module 5's tests exercised the gap directly. Fixed all of them in
this delivery:
- `staff/migrations/0001_initial.py` — corrected directly (this app
  hasn't shipped to you before now, so there's no prior migration
  history to preserve).
- `venues/migrations/0002_...py`, `resources/migrations/0002_...py`,
  `vendors/migrations/0002_...py` — new migrations added on top of the
  already-shipped ones (the correct way to evolve a schema — never edit
  a migration that's already been applied). These are schema-neutral at
  the database level (`blank` is Python/validation-only, not a DB
  constraint), so applying them is a formality, not a data change — and
  it was still verified end-to-end against your real `db.sqlite3`.
- `vendors/migrations/0001_initial.py` was **not** edited — Module 4's
  original migration ships as-is; the fix layers on top via 0002.
- `venues/models.py`, `resources/models.py`, `vendors/models.py`,
  `staff/models.py` — all corrected. No existing behavior changes: these
  fields were always being populated by the views in practice, so this
  fix only affects edge cases (direct model use without every field set,
  and the moment an audit-trail user account is ever deleted).
- `staff/tests.py` — 20 tests covering conflict detection (including
  cancelled shifts not blocking, back-to-back non-overlap),
  `find_available` filtering by department/skill/active-status,
  onboarding permissions and role promotion, shift-assignment
  permissions, auto-assign (both a successful match and a
  no-match-found path), and salary/attendance visibility rules.
  Combined with Modules 1–4, **82/82 tests pass.**
- Also smoke-tested manually end-to-end through the real views:
  department created → staff onboarded (role promoted) → shift assigned
  → a conflicting second assignment correctly rejected → auto-assign
  correctly picks the free, skill-matching staff member over the busy
  one → self-attendance marked → blocked from marking someone else's →
  salary record added with correct net amount → salary confidentiality
  verified by inspecting rendered page content, not just view context.

**Not built yet (intentionally deferred):** a shift calendar view like
venues' (staff shifts are single-person/exclusive like venues, not
pooled like resources, so a calendar would be a natural fit — deferred
for the same reason resources' calendar was: it pairs more naturally
with Module 8's Reports & Analytics, which is when "staff performance
report" is built anyway).

## ✅ Module 6 — Budget & Expense Tracking (DONE, this delivery)

**What's new:**
- New `budget` app: `EventBudget`, `Expense`, `RevenueEntry` models.
- **`EventBudget`** is one-to-one with `Event` (same anchor pattern as
  `VendorContract` off `VendorProfile`) and holds `estimated_budget`, set
  at planning time. `total_expenses`, `total_revenue`, and
  `profit_or_loss` are **never stored** — they're computed live from the
  related rows every time they're read, the same "derive it from real
  rows" approach `VendorContract.balance_due` uses, so these numbers
  can't go stale relative to the underlying Expense/RevenueEntry/
  VendorPayment records.
- **Expense categories match the spec exactly**: Venue, Catering,
  Marketing, Staff, Equipment, Travel, Miscellaneous. Each expense also
  has a status (`pending` / `approved` / `paid`) — **only approved/paid
  expenses count toward "actual" spend**, so logging an expense never
  silently finalizes it. Verified: a `pending` ₹5,000 expense leaves
  `total_expenses` at ₹0; moving it to `paid` immediately brings the
  live total to ₹5,000, no save/recalculate step needed anywhere else.
- **Revenue** covers ticket sales, sponsorship, and manual/other entries.
  Ticket-sales entries are manual for now — Module 7 (Ticketing) will
  generate them automatically from Registration/ticket data once that
  model exists, without any schema change here. Sponsorship carries a
  free-text `sponsor_name` (required when source is Sponsorship,
  enforced in `clean()`) as a stand-in until a real Sponsor model exists
  to link to.
- **Vendor payments are reused, not duplicated.** `EventBudget.total_expenses`
  = confirmed direct `Expense` rows + `paid` `VendorPayment` rows (via
  Module 4's `VendorContract.event`) — a vendor payment already *is* an
  expense, so tracking it twice would let the two numbers drift apart.
  Verified: a ₹4,000 paid vendor payment shows up in `total_expenses`
  automatically; a `pending` vendor payment on a second contract for the
  same event correctly does **not** count until it's marked paid.
- **Budget vs. actual variance** — `variance = estimated_budget -
  total_expenses`, with an `is_over_budget` flag and a category-level
  breakdown (`EventBudget.category_breakdown`) grouping confirmed
  expenses by category plus a synthetic "Vendor Payments" row, since
  `VendorPayment` has no category of its own. This is the data Module 8's
  Expense/Budget Reports will chart — this module produces the numbers,
  Module 8 turns them into exports and visualizations.
- **Permissions match the spec's wording precisely**: Organizer (for
  their own events) and Staff/Super Admin can set up a budget, log
  expenses/revenue, and view budget vs. actual; no separate approver
  role was invented beyond that — the same set of people who can log a
  line item can also move its status along. Verified: an organizer can
  set up and manage their own event's budget; a *different* organizer is
  correctly blocked from another organizer's event budget; Staff can
  manage any event's budget; a Participant is redirected away from the
  budget area entirely.
- **Read-only summaries surfaced where the spec asked for them**: a
  budget summary card on the event detail page (estimate / spent /
  revenue / variance, visible only to whoever can manage that event's
  finances) and an extension of the Module 1 dashboard — organizers see
  totals across their own events' budgets, Super Admin sees system-wide
  revenue/expenses/net-profit/vendor-payments alongside the existing
  event and user counts (replacing the "lights up once Budget exists"
  placeholder note from Module 1).
- `budget/migrations/0001_initial.py` — hand-verified against your real
  `db.sqlite3` (`makemigrations --check` reports zero drift anywhere else
  in the project, migration applied cleanly, all 7 existing events and
  both users intact afterward).
- `budget/tests.py` — 13 tests covering the variance/profit math
  (zero-state, pending-doesn't-count, approved/paid counts, over-budget
  flag), revenue totals and profit/loss, the sponsorship-requires-a-name
  validation, vendor-payment reuse (including that a pending vendor
  payment doesn't count), category breakdown correctness, and the full
  permission matrix (organizer-owns-it, other-organizer-blocked,
  staff-can-manage-any, participant-blocked). Combined with Modules
  1–5, **95/95 tests pass.**
- Also smoke-tested manually end-to-end through the real views (not just
  the test suite): event created → budget set up (₹20,000 estimate) →
  event detail page correctly prompts "Set Up Budget" beforehand and
  shows the live summary afterward → expense logged as `pending`
  (`total_expenses` stays ₹0) → marked `paid` (`total_expenses` updates
  to ₹5,000 with no other step) → ticket-sales revenue of ₹15,000 added
  → profit/loss and variance both compute correctly (₹10,000 profit,
  ₹15,000 under budget) → dashboard renders the new "My Budgets" panel
  for the organizer and the system-wide financial row for Super Admin →
  a Participant is correctly redirected away from `/budget/`. All test
  data was created and removed via the ORM; your real 7 events / 2 users
  are unchanged.

**Not built yet (intentionally deferred):** downloadable Budget/Expense
Reports (PDF/CSV/Excel) and charts — this module produces the numbers
(`category_breakdown`, live totals) that Module 8 (Reports & Analytics)
is specifically for, so building export/chart UI here would duplicate
that module's job; automatic ticket-sales revenue rows (currently
manual, becomes automatic once Module 7's Registration/ticket data
exists — no schema change needed when that lands); a real `Sponsor`
model to replace the free-text `sponsor_name` field.

## 🔜 Upcoming modules (in order)

7. **Ticketing & QR Check-in** — QR/PDF/email tickets, scanner, duplicate-scan prevention
8. **Reports & Analytics** — PDF/CSV/Excel exports, interactive charts
9. **Workflow, Notifications & Calendar** — approval pipeline, reminders, monthly/weekly views
10. **Premium/AI features** — recommendations, predictions, gamification, etc. (last, since they depend on data from modules 2–9)

Each module will ship the same way: real code, a migration tested against
your live data, a test suite, and an explicit note on any behavior change.

## How to run this

```bash
# from the project root
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Your existing superuser/admin account keeps working exactly as before —
it was auto-upgraded to `role=organizer` by the migration and, as a
superuser, always passes every role check regardless of `role`.
