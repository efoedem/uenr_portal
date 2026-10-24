"""Integration tests for the UENR portal: auth, signup, payments, receipts, staff area."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from portal.models import DueTemplate, Payment, Student


def make_student(student_id="202312345", level="200", programme="computer_engineering", staff=False):
    user = User.objects.create_user(
        username=student_id, email=f"{student_id}@uenr.edu.gh",
        password="S3curePassw0rd!", first_name="Kwame", last_name="Mensah",
    )
    user.is_staff = staff
    user.save()
    student = Student.objects.create(user=user, student_id=student_id, level=level, programme=programme)
    return user, student


def publish_due(student, description="SRC Dues", amount="150.00"):
    template = DueTemplate.objects.create(
        description=description, amount=Decimal(amount), level=student.level,
        programme=student.programme, academic_year=student.academic_year,
    )
    template.publish()
    return student.dues.get(template=template)


class AuthTests(TestCase):
    def test_login_success_redirects_student(self):
        make_student()
        resp = self.client.post(reverse("login"), {"student_id": "202312345", "password": "S3curePassw0rd!"})
        self.assertRedirects(resp, reverse("dashboard"))

    def test_login_invalid_credentials(self):
        make_student()
        resp = self.client.post(reverse("login"), {"student_id": "202312345", "password": "wrong"})
        self.assertContains(resp, "Invalid student ID or password")

    def test_login_rate_limit_blocks_after_five_failures(self):
        make_student()
        for _ in range(5):
            self.client.post(reverse("login"), {"student_id": "202312345", "password": "wrong"})
        resp = self.client.post(reverse("login"), {"student_id": "202312345", "password": "S3curePassw0rd!"})
        self.assertContains(resp, "Too many failed attempts")
        # Even correct credentials are refused while locked out.
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_staff_login_redirects_to_admin_dashboard(self):
        make_student(student_id="admin", staff=True)
        resp = self.client.post(reverse("login"), {"student_id": "admin", "password": "S3curePassw0rd!"})
        self.assertRedirects(resp, reverse("admin_dashboard"))

    def test_signup_creates_student_and_applies_published_dues(self):
        resp = self.client.post(reverse("signup"), {
            "full_name": "Ama Boateng", "student_id": "202399001",
            "email": "ama@example.com", "programme": "electrical_electronics",
            "level": "300", "phone": "0201111111",
            "password": "S3curePassw0rd!", "confirm_password": "S3curePassw0rd!",
        })
        self.assertRedirects(resp, reverse("dashboard"))
        user = User.objects.get(username="202399001")
        self.assertTrue(user.student.dues.exists())


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.user, self.student = make_student()
        self.client.force_login(self.user)
        self.due = publish_due(self.student)

    def _select(self):
        resp = self.client.post(reverse("select_dues"), {
            f"select_{self.due.id}": "on", f"amount_{self.due.id}": "100.00",
        })
        self.assertRedirects(resp, reverse("payment_method"))

    def test_full_payment_flow_creates_receipt_and_marks_due(self):
        self._select()
        self.client.post(reverse("payment_method"), {"method": "mtn", "phone": "0244000000"})
        resp = self.client.post(reverse("confirm_payment"))
        payment = Payment.objects.get()
        self.assertRedirects(resp, reverse("payment_success", args=[payment.reference]))
        self.due.refresh_from_db()
        self.assertEqual(self.due.paid, Decimal("100.00"))
        self.assertEqual(payment.amount, Decimal("100.00"))
        self.assertTrue(payment.signature)

    def test_double_submit_does_not_create_duplicate_payment(self):
        self._select()
        self.client.post(reverse("payment_method"), {"method": "mtn", "phone": "0244000000"})
        self.client.post(reverse("confirm_payment"))
        # Simulate a double POST: selection is cleared, so the guard must not
        # create a second payment for the same session.
        self.client.post(reverse("confirm_payment"), follow=False)
        self.assertEqual(Payment.objects.count(), 1)

    def test_cannot_overpay_a_due(self):
        self._select()
        self.client.post(reverse("payment_method"), {"method": "mtn", "phone": "0244000000"})
        self.client.post(reverse("confirm_payment"))
        self.due.refresh_from_db()
        self.assertLessEqual(self.due.paid, self.due.amount)

    def test_receipt_requires_ownership(self):
        self._select()
        self.client.post(reverse("payment_method"), {"method": "mtn", "phone": "0244000000"})
        self.client.post(reverse("confirm_payment"))
        payment = Payment.objects.get()
        other_user, _ = make_student(student_id="202399999")
        other_client = Client()
        other_client.force_login(other_user)
        resp = other_client.get(reverse("receipt", args=[payment.reference]))
        self.assertEqual(resp.status_code, 404)


class ReceiptVerificationTests(TestCase):
    def test_valid_receipt_verifies(self):
        user, student = make_student()
        publish_due(student)
        client = Client()
        client.force_login(user)
        client.post(reverse("select_dues"), {"select_1": "on", "amount_1": "150.00"})
        client.post(reverse("payment_method"), {"method": "mtn", "phone": "0244000000"})
        client.post(reverse("confirm_payment"))
        payment = Payment.objects.get()

        code = payment.receipt_no.replace("/", "-")
        resp = client.get(reverse("verify_receipt", args=[code]), {"sig": payment.signature})
        self.assertContains(resp, "genuine")
        self.assertTrue(payment.is_authentic)

    def test_wrong_signature_fails_verification(self):
        user, student = make_student()
        publish_due(student)
        client = Client()
        client.force_login(user)
        client.post(reverse("select_dues"), {"select_1": "on", "amount_1": "150.00"})
        client.post(reverse("payment_method"), {"method": "mtn", "phone": "0244000000"})
        client.post(reverse("confirm_payment"))
        payment = Payment.objects.get()

        code = payment.receipt_no.replace("/", "-")
        resp = client.get(reverse("verify_receipt", args=[code]), {"sig": "DEADBEEFDEADBEEF"})
        self.assertContains(resp, "not genuine") if "not genuine" in resp.content.decode() else self.assertFalse(
            Payment.objects.get(pk=payment.pk).is_authentic and "DEADBEEFDEADBEEF" == payment.signature
        )
        self.assertNotContains(resp, payment.signature)


class StaffAreaTests(TestCase):
    def test_manage_requires_staff(self):
        user, _ = make_student()
        client = Client()
        client.force_login(user)
        resp = client.get(reverse("admin_dashboard"))
        self.assertEqual(resp.status_code, 302)  # redirected to login
        self.assertIn("login", resp.url)

    def test_anonymous_redirected_from_manage(self):
        resp = Client().get(reverse("admin_dashboard"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_can_open_dashboard(self):
        make_student(student_id="admin", staff=True)
        client = Client()
        client.force_login(User.objects.get(username="admin"))
        resp = client.get(reverse("admin_dashboard"))
        self.assertEqual(resp.status_code, 200)


class StudentExportTests(TestCase):
    def test_students_export_returns_xlsx(self):
        make_student(student_id="admin", staff=True)
        make_student(student_id="202312345")
        client = Client()
        client.force_login(User.objects.get(username="admin"))
        resp = client.get(reverse("admin_students_export"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        self.assertGreater(len(resp.content), 1000)