import hashlib
import hmac
import secrets
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models

PAYMENT_METHODS = [
    ("mtn", "MTN Mobile Money"),
    ("vodafone", "Vodafone Cash"),
    ("card", "Card Payment"),
    ("bank", "Bank Transfer"),
]

PROGRAMMES = [
    ("computer_engineering", "Computer Engineering"),
    ("electrical_electronics", "Electrical and Electronics Engineering"),
]

LEVELS = [
    ("100", "Level 100"),
    ("200", "Level 200"),
    ("300", "Level 300"),
    ("400", "Level 400"),
]


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student")
    student_id = models.CharField("Index number", max_length=20, unique=True)
    programme = models.CharField(max_length=40, choices=PROGRAMMES, blank=True)
    level = models.CharField(max_length=5, choices=LEVELS, default="100")
    phone = models.CharField(max_length=20, blank=True)
    academic_year = models.CharField(max_length=20, default="2025/2026")

    class Meta:
        ordering = ["level", "student_id"]

    def __str__(self):
        return f"{self.full_name} ({self.student_id})"

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def programme_label(self):
        return dict(PROGRAMMES).get(self.programme, self.programme or "—")

    @property
    def programme_short(self):
        return {"computer_engineering": "COE", "electrical_electronics": "EEE"}.get(
            self.programme, "—"
        )

    @property
    def level_label(self):
        return f"Level {self.level}" if self.level else "—"

    @property
    def total_dues(self):
        return sum((d.amount for d in self.dues.all()), Decimal("0"))

    @property
    def total_paid(self):
        return sum((d.paid for d in self.dues.all()), Decimal("0"))

    @property
    def outstanding(self):
        return self.total_dues - self.total_paid

    @property
    def progress(self):
        if not self.total_dues:
            return 0
        return int(self.total_paid / self.total_dues * 100)


class DueTemplate(models.Model):
    """A due published by the admin to a whole level (optionally one programme)."""

    description = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    level = models.CharField(max_length=5, choices=LEVELS)
    programme = models.CharField(
        max_length=40, choices=PROGRAMMES, blank=True,
        help_text="Leave blank to publish to both programmes.",
    )
    academic_year = models.CharField(max_length=20, default="2025/2026")
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.description} · Level {self.level}"

    def matching_students(self):
        qs = Student.objects.filter(level=self.level)
        if self.programme:
            qs = qs.filter(programme=self.programme)
        return qs

    def publish(self):
        """Give this due to every matching student who does not already have it."""
        created = 0
        for student in self.matching_students():
            _, made = Due.objects.get_or_create(
                student=student,
                template=self,
                defaults={"description": self.description, "amount": self.amount},
            )
            if made:
                created += 1
        return created


class Due(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="dues")
    template = models.ForeignKey(
        DueTemplate, on_delete=models.CASCADE, related_name="dues", null=True, blank=True
    )
    description = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.description

    @property
    def balance(self):
        return self.amount - self.paid

    @property
    def status(self):
        if self.balance <= 0:
            return "Paid"
        if self.paid > 0:
            return "Partial"
        return "Outstanding"


class Payment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="payments")
    reference = models.CharField(max_length=40, unique=True)
    receipt_no = models.CharField(max_length=40, unique=True)
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    phone_number = models.CharField(max_length=20, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    level = models.CharField(max_length=5, blank=True)
    programme = models.CharField(max_length=40, blank=True)
    signature = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference

    @property
    def method_label(self):
        return dict(PAYMENT_METHODS).get(self.method, self.method)

    @property
    def programme_label(self):
        return dict(PROGRAMMES).get(self.programme, self.programme or "—")

    @staticmethod
    def new_reference():
        return "PSK_" + secrets.token_hex(4).upper()

    def build_signature(self):
        raw = "|".join(
            [
                self.receipt_no,
                self.reference,
                self.student.student_id,
                f"{self.amount:.2f}",
                self.created_at.isoformat() if self.created_at else "",
            ]
        )
        digest = hmac.new(
            settings.SECRET_KEY.encode(), raw.encode(), hashlib.sha256
        ).hexdigest()
        return digest[:16].upper()

    @property
    def signature_pretty(self):
        s = self.signature or ""
        return "-".join(s[i:i + 4] for i in range(0, len(s), 4))

    @property
    def is_authentic(self):
        return bool(self.signature) and hmac.compare_digest(
            self.signature, self.build_signature()
        )


class PaymentItem(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="items")
    due = models.ForeignKey(Due, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.due.description} - {self.amount}"
