# Eventra — Smart Event Planning Platform with Resource coordination system

A full-stack, production-quality event management platform built with **Django 5**,
**Bootstrap 5**, **Bootstrap Icons**, and **SQLite**. EventSphere lets organizers create
and manage events, and lets attendees discover, search, and register for them — all
through a modern, glassmorphism-styled SaaS-style interface.

No custom JavaScript is used anywhere in the project — only Bootstrap's own bundled JS
(`bootstrap.bundle.min.js`), which is required for the responsive navbar, dropdowns, and
dismissible alerts to function.

---

## Tech Stack

| Layer      | Technology                          |
|------------|--------------------------------------|
| Backend    | Python, Django 5                     |
| Frontend   | HTML5, Bootstrap 5, CSS3             |
| Icons      | Bootstrap Icons                      |
| Database   | SQLite                               |
| Fonts      | Google Fonts — Poppins               |

---

## Project Structure

```
Event_Management_System/
├── event_management/       # Project settings, root URLs, static-page views
├── users/                   # Custom User model, auth, profile
├── events/                  # Event + Registration models, views, forms
├── categories/               # Category model, views, forms
├── dashboard/                # Aggregated stats dashboard
├── templates/
│   ├── includes/             # navbar.html, footer.html, sidebar.html, messages.html
│   ├── pages/                # about, contact, faq, privacy, terms
│   ├── profile/              # profile, edit_profile, change_password
│   ├── registration/         # login, signup, password reset flow
│   ├── dashboard/            # dashboard.html
│   ├── events/                # list, detail, form, my_events, my_registrations, confirms
│   ├── categories/            # list, form, confirm_delete
│   ├── errors/                # 404.html
│   ├── base.html
│   └── home.html
├── static/
│   ├── css/
│   │   ├── style.css          # global theme, layout, cards, buttons, badges
│   │   ├── auth.css           # login/signup/reset pages
│   │   ├── forms.css          # form controls, floating labels
│   │   ├── events.css         # event cards, filters, progress bars
│   │   ├── dashboard.css      # sidebar + dashboard stat cards
│   │   └── responsive.css     # breakpoints
│   ├── images/
│   └── icons/
├── media/
│   ├── event_images/
│   └── profile_images/
├── manage.py
├── requirements.txt
└── db.sqlite3
```

---

## Features

### Authentication (users app)
- Sign up, log in, log out
- Forgot / reset password (Django's built-in token flow, console email backend)
- View & edit profile (name, email, phone, bio, profile picture)
- Change password

### Events (events app)
- Create / update / delete events (organizer or staff only)
- Public event listing with **search** + **category filter** + **pagination**
- Event detail page with seat-capacity progress bar
- Register / cancel registration
- "My Events" (events you organize) and "My Registrations" (events you're attending)

### Categories (categories app)
- List categories with live event counts
- Add / edit / delete categories (staff only)

### Dashboard (dashboard app)
- Total events, categories, participants, and registrations
- Upcoming events, recent registrations, recent events
- Quick actions panel

### Design
- Dark blue theme (`#0F172A` background) with glassmorphism cards
- 16px rounded corners, generous spacing, Bootstrap shadows
- CSS-only hover animations (no JS)
- Poppins typography throughout
- Fully responsive (mobile, tablet, desktop)

---

## Getting Started

### 1. Create a virtual environment & install dependencies
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Apply migrations
```bash
python manage.py migrate
```
(A `db.sqlite3` with sample categories, sample events, and a superuser is already
included — you can skip straight to step 4 if you'd like to explore immediately.)

### 3. Create a superuser (only needed if you reset the database)
```bash
python manage.py createsuperuser
```

### 4. Run the development server
```bash
python manage.py runserver
```
Visit **http://127.0.0.1:8000/**

### Demo login (included in the shipped database)
```
Username: admin
Password: Admin@12345
```
This account is a superuser and organizer, so it can create events, manage categories,
and access Django admin at `/admin/`.

---

## Notes for Presentation / Evaluation

- Each Django app (`users`, `events`, `categories`, `dashboard`) is self-contained with
  its own `models.py`, `forms.py`, `views.py`, `urls.py`, and `admin.py` — easy to walk
  through module by module.
- All forms use Django `ModelForm`s with server-side validation and Bootstrap floating
  labels / styled inputs.
- Access control: only an event's organizer (or staff) can edit/delete it; only staff
  can manage categories.
- `EMAIL_BACKEND` is set to the console backend for development, so password-reset
  emails print to the terminal instead of being sent — swap in a real SMTP backend for
  production.
