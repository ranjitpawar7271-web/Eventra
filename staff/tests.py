from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import User
from .models import AttendanceRecord, Department, SalaryRecord, ShiftAssignment, StaffProfile

_BASE_TIME = timezone.now()


def dt(hours_from_base):
    return _BASE_TIME + timedelta(hours=hours_from_base)


class StaffProfileModelTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Operations')
        self.staff_user = User.objects.create_user(username='suser', password='pw12345!', role=User.STAFF)
        self.profile = StaffProfile.objects.create(
            user=self.staff_user, employee_id='EMP-001', department=self.dept, skills='First Aid, Crowd Control',
        )

    def test_skill_list_parses_csv(self):
        self.assertEqual(self.profile.skill_list, ['First Aid', 'Crowd Control'])

    def test_available_with_no_shifts(self):
        self.assertTrue(self.profile.is_available(dt(1), dt(2)))

    def test_shift_blocks_overlapping_window(self):
        ShiftAssignment.objects.create(
            staff=self.profile, title='Gate Duty', start_datetime=dt(1), end_datetime=dt(3), status='assigned',
        )
        self.assertFalse(self.profile.is_available(dt(2), dt(4)))
        self.assertTrue(self.profile.is_available(dt(3), dt(5)))  # back-to-back, no overlap

    def test_cancelled_shift_does_not_block(self):
        ShiftAssignment.objects.create(
            staff=self.profile, title='Gate Duty', start_datetime=dt(1), end_datetime=dt(3), status='cancelled',
        )
        self.assertTrue(self.profile.is_available(dt(1), dt(3)))

    def test_double_booking_shift_creation_rejected(self):
        ShiftAssignment.objects.create(
            staff=self.profile, title='Gate Duty', start_datetime=dt(1), end_datetime=dt(3), status='assigned',
        )
        with self.assertRaises(Exception):
            ShiftAssignment.objects.create(
                staff=self.profile, title='Registration Desk', start_datetime=dt(2), end_datetime=dt(4), status='assigned',
            )


class FindAvailableStaffTests(TestCase):
    def setUp(self):
        self.dept_a = Department.objects.create(name='Security')
        self.dept_b = Department.objects.create(name='Logistics')

        u1 = User.objects.create_user(username='sfa1', password='pw12345!', role=User.STAFF)
        u2 = User.objects.create_user(username='sfa2', password='pw12345!', role=User.STAFF)
        u3 = User.objects.create_user(username='sfa3', password='pw12345!', role=User.STAFF)

        self.busy = StaffProfile.objects.create(user=u1, employee_id='E1', department=self.dept_a, skills='First Aid')
        self.free_matching = StaffProfile.objects.create(user=u2, employee_id='E2', department=self.dept_a, skills='First Aid, CPR')
        self.free_wrong_dept = StaffProfile.objects.create(user=u3, employee_id='E3', department=self.dept_b, skills='First Aid')

        ShiftAssignment.objects.create(
            staff=self.busy, title='Busy shift', start_datetime=dt(1), end_datetime=dt(3), status='assigned',
        )

    def test_excludes_conflicting_staff(self):
        results = StaffProfile.find_available(dt(2), dt(4))
        self.assertNotIn(self.busy, results)
        self.assertIn(self.free_matching, results)

    def test_filters_by_department(self):
        results = StaffProfile.find_available(dt(5), dt(6), department=self.dept_a)
        self.assertIn(self.free_matching, results)
        self.assertNotIn(self.free_wrong_dept, results)

    def test_filters_by_skill(self):
        results = StaffProfile.find_available(dt(5), dt(6), skill='CPR')
        self.assertIn(self.free_matching, results)
        self.assertNotIn(self.free_wrong_dept, results)

    def test_inactive_staff_excluded(self):
        self.free_matching.is_active = False
        self.free_matching.save()
        results = StaffProfile.find_available(dt(5), dt(6))
        self.assertNotIn(self.free_matching, results)


class StaffOnboardingViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='soadmin', password='pw12345!', role=User.SUPER_ADMIN)
        self.organizer = User.objects.create_user(username='soorg', password='pw12345!', role=User.ORGANIZER)
        self.target = User.objects.create_user(username='sotarget', password='pw12345!')  # plain participant

    def test_organizer_cannot_onboard_staff(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('staff:staff_onboard'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_admin_can_onboard_staff_and_role_is_promoted(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff:staff_onboard'), {
            'username': 'sotarget', 'employee_id': 'EMP-100', 'department': '',
            'designation': 'Coordinator', 'phone_number': '', 'skills': 'Logistics',
            'hire_date': date.today().isoformat(), 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, User.STAFF)
        self.assertTrue(StaffProfile.objects.filter(user=self.target).exists())

    def test_cannot_onboard_already_onboarded_user(self):
        StaffProfile.objects.create(user=self.target, employee_id='EMP-200')
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff:staff_onboard'), {
            'username': 'sotarget', 'employee_id': 'EMP-201', 'department': '',
            'designation': '', 'phone_number': '', 'skills': '',
            'hire_date': date.today().isoformat(), 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 200)  # re-rendered with form error
        self.assertEqual(StaffProfile.objects.filter(user=self.target).count(), 1)


class ShiftAndAutoAssignViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='saadmin', password='pw12345!', role=User.SUPER_ADMIN)
        self.organizer = User.objects.create_user(username='saorg', password='pw12345!', role=User.ORGANIZER)
        self.participant = User.objects.create_user(username='sapart', password='pw12345!')
        staff_user = User.objects.create_user(username='saworker', password='pw12345!', role=User.STAFF)
        self.dept = Department.objects.create(name='Front of House')
        self.profile = StaffProfile.objects.create(
            user=staff_user, employee_id='EMP-300', department=self.dept, skills='Ushering',
        )

    def test_participant_cannot_assign_shift(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse('staff:shift_assign'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_organizer_can_assign_shift(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('staff:shift_assign'), {
            'staff': self.profile.pk, 'event': '', 'title': 'Ushering',
            'start_datetime': dt(1).strftime('%Y-%m-%dT%H:%M'),
            'end_datetime': dt(3).strftime('%Y-%m-%dT%H:%M'), 'notes': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ShiftAssignment.objects.filter(staff=self.profile).count(), 1)

    def test_auto_assign_finds_and_creates_shift(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff:shift_auto_assign'), {
            'title': 'Registration Desk', 'department': self.dept.pk, 'skill': 'Usher',
            'start_datetime': dt(5).strftime('%Y-%m-%dT%H:%M'),
            'end_datetime': dt(7).strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertEqual(response.status_code, 302)
        shift = ShiftAssignment.objects.get(staff=self.profile)
        self.assertTrue(shift.auto_assigned)

    def test_auto_assign_no_match_shows_warning_not_error(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff:shift_auto_assign'), {
            'title': 'Impossible', 'department': '', 'skill': 'Nonexistent Skill XYZ',
            'start_datetime': dt(5).strftime('%Y-%m-%dT%H:%M'),
            'end_datetime': dt(7).strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShiftAssignment.objects.count(), 0)


class SalaryAndAttendanceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='slaadmin', password='pw12345!', role=User.SUPER_ADMIN)
        self.staff_user = User.objects.create_user(username='slaworker', password='pw12345!', role=User.STAFF)
        self.other_staff_user = User.objects.create_user(username='slaother', password='pw12345!', role=User.STAFF)
        self.profile = StaffProfile.objects.create(user=self.staff_user, employee_id='EMP-400')
        self.other_profile = StaffProfile.objects.create(user=self.other_staff_user, employee_id='EMP-401')

    def test_net_amount_calculation(self):
        record = SalaryRecord.objects.create(
            staff=self.profile, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
            basic_amount=30000, bonus=2000, deductions=1500,
        )
        self.assertEqual(record.net_amount, 30500)

    def test_only_admin_can_add_salary_record(self):
        self.client.force_login(self.staff_user)  # self, but not admin
        response = self.client.get(reverse('staff:salary_record_create', args=[self.profile.pk]))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_staff_can_self_mark_attendance(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('staff:attendance_mark', args=[self.profile.pk]))
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_mark_others_attendance(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('staff:attendance_mark', args=[self.other_profile.pk]))
        self.assertRedirects(response, reverse('staff:staff_detail', args=[self.other_profile.pk]))

    def test_salary_only_visible_to_self_or_admin(self):
        SalaryRecord.objects.create(
            staff=self.profile, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31), basic_amount=25000,
        )
        # another staff member should not see it
        self.client.force_login(self.other_staff_user)
        response = self.client.get(reverse('staff:staff_detail', args=[self.profile.pk]))
        self.assertEqual(list(response.context['salary_records']), [])
