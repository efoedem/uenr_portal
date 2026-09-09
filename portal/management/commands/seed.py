from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from portal.models import DueTemplate, Student

DUE_TEMPLATES = [
    ("Academic Facility User Fee", 2500, "100", ""),
    ("Departmental Dues", 300, "100", ""),
    ("SRC Dues", 200, "100", ""),
    ("Departmental Dues", 350, "200", ""),
    ("SRC Dues", 200, "200", ""),
    ("Laboratory Dues", 250, "300", "electrical_electronics"),
    ("Project Fund", 400, "400", ""),
]

DEMO_STUDENTS = [
    ("202312345", "John", "Mensah", "100", "computer_engineering", "0244000001"),
    ("202312346", "Ama", "Boateng", "200", "electrical_electronics", "0244000002"),
    ("202312347", "Kofi", "Owusu", "300", "electrical_electronics", "0244000003"),
    ("202312348", "Akua", "Sarpong", "400", "computer_engineering", "0244000004"),
]


class Command(BaseCommand):
    help = "Create an admin account, published dues and demo students."

    def handle(self, *args, **options):
        for description, amount, level, programme in DUE_TEMPLATES:
            DueTemplate.objects.get_or_create(
                description=description, level=level, programme=programme,
                defaults={"amount": amount},
            )

        for student_id, first, last, level, programme, phone in DEMO_STUDENTS:
            user, _ = User.objects.get_or_create(
                username=student_id,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": f"{first.lower()}@uenr.edu.gh",
                },
            )
            user.set_password("password123")
            user.save()
            Student.objects.get_or_create(
                user=user,
                defaults={
                    "student_id": student_id, "level": level,
                    "programme": programme, "phone": phone,
                },
            )

        for template in DueTemplate.objects.all():
            template.publish()

        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@uenr.edu.gh", "admin123")

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data ready.\n"
                "  Student: 202312345 / password123\n"
                "  Admin:   admin / admin123"
            )
        )
