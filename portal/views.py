from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from .models import LEVELS, PAYMENT_METHODS, PROGRAMMES, Due, DueTemplate, Payment, PaymentItem, Student
from .utils import qr_data_uri


def _student(request):
    student, _ = Student.objects.get_or_create(
        user=request.user,
        defaults={"student_id": request.user.username},
    )
    return student


def landing(request):
    return render(request, "portal/landing.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        student_id = request.POST.get("student_id", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=student_id, password=password)
        if user is not None:
            login(request, user)
            if user.is_staff:
                return redirect("admin_dashboard")
            return redirect("dashboard")
        messages.error(request, "Invalid student ID or password.")
    return render(request, "portal/login.html")


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        student_id = request.POST.get("student_id", "").strip()
        email = request.POST.get("email", "").strip()
        programme = request.POST.get("programme", "").strip()
        level = request.POST.get("level", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        confirm = request.POST.get("confirm_password", "")
        valid_programmes = dict(PROGRAMMES)
        valid_levels = dict(LEVELS)

        if not student_id or not password:
            messages.error(request, "Index number and password are required.")
        elif not email:
            messages.error(request, "An email is required so you can reset your password.")
        elif programme not in valid_programmes:
            messages.error(request, "Choose your programme.")
        elif level not in valid_levels:
            messages.error(request, "Choose your level.")
        elif password != confirm:
            messages.error(request, "Passwords do not match.")
        elif len(password) < 6:
            messages.error(request, "Password must be at least 6 characters.")
        elif User.objects.filter(username=student_id).exists():
            messages.error(request, "An account with that index number already exists.")
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, "That email is already registered.")
        else:
            first, _, last = full_name.partition(" ")
            user = User.objects.create_user(
                username=student_id, email=email, password=password,
                first_name=first, last_name=last,
            )
            student = Student.objects.create(
                user=user, student_id=student_id, programme=programme,
                level=level, phone=phone,
            )
            # Only dues published by the admin for this level/programme apply.
            for template in DueTemplate.objects.filter(level=level):
                if template.programme and template.programme != programme:
                    continue
                Due.objects.get_or_create(
                    student=student, template=template,
                    defaults={"description": template.description, "amount": template.amount},
                )
            login(request, user)
            messages.success(request, "Account created. Welcome to the portal!")
            return redirect("dashboard")
    return render(
        request,
        "portal/signup.html",
        {"programmes": PROGRAMMES, "levels": LEVELS},
    )


def logout_view(request):
    logout(request)
    return redirect("landing")


@login_required
def dashboard(request):
    student = _student(request)
    return render(
        request,
        "portal/dashboard.html",
        {"student": student, "dues": student.dues.all(), "active": "dashboard"},
    )


@login_required
def profile(request):
    student = _student(request)
    if request.method == "POST":
        student.phone = request.POST.get("phone", "").strip()
        level = request.POST.get("level", "").strip()
        programme = request.POST.get("programme", "").strip()
        if level in dict(LEVELS):
            student.level = level
        if programme in dict(PROGRAMMES):
            student.programme = programme
        student.save()
        request.user.first_name = request.POST.get("first_name", "").strip()
        request.user.last_name = request.POST.get("last_name", "").strip()
        request.user.email = request.POST.get("email", "").strip()
        request.user.save()
        messages.success(request, "Profile updated.")
        return redirect("profile")
    return render(
        request,
        "portal/profile.html",
        {"student": student, "levels": LEVELS, "programmes": PROGRAMMES, "active": "profile"},
    )


@login_required
def select_dues(request):
    student = _student(request)
    dues = student.dues.all()
    if request.method == "POST":
        selection = {}
        for due in dues:
            if request.POST.get(f"select_{due.id}"):
                raw = request.POST.get(f"amount_{due.id}", "0")
                try:
                    amount = Decimal(raw)
                except (InvalidOperation, TypeError):
                    amount = Decimal("0")
                amount = min(max(amount, Decimal("0")), due.balance)
                if amount > 0:
                    selection[str(due.id)] = str(amount)
        if not selection:
            messages.error(request, "Select at least one due with an amount to pay.")
        else:
            request.session["selection"] = selection
            return redirect("payment_method")
    return render(
        request,
        "portal/select_dues.html",
        {"student": student, "dues": dues, "active": "pay"},
    )


@login_required
def payment_method(request):
    student = _student(request)
    selection = request.session.get("selection")
    if not selection:
        return redirect("select_dues")
    total = sum(Decimal(v) for v in selection.values())
    if request.method == "POST":
        method = request.POST.get("method")
        phone = request.POST.get("phone", "").strip()
        if method not in dict(PAYMENT_METHODS):
            messages.error(request, "Choose a payment method.")
        elif method in ("mtn", "vodafone") and len(phone) < 9:
            messages.error(request, "Enter the mobile money number used for this payment.")
        else:
            request.session["method"] = method
            request.session["phone"] = phone
            return redirect("confirm_payment")
    return render(
        request,
        "portal/payment_method.html",
        {
            "student": student, "total": total, "methods": PAYMENT_METHODS,
            "active": "pay",
        },
    )


@login_required
def confirm_payment(request):
    """Simulated payment processing: marks dues paid and creates a signed receipt."""
    student = _student(request)
    selection = request.session.get("selection")
    method = request.session.get("method")
    if not selection or not method:
        return redirect("select_dues")

    total = sum(Decimal(v) for v in selection.values())
    reference = Payment.new_reference()
    count = Payment.objects.count() + 1
    payment = Payment.objects.create(
        student=student,
        reference=reference,
        receipt_no=f"UENR/{student.academic_year.split('/')[0]}/{count:07d}",
        method=method,
        phone_number=request.session.get("phone", "") or student.phone,
        amount=total,
        level=student.level,
        programme=student.programme,
    )
    payment.signature = payment.build_signature()
    payment.save(update_fields=["signature"])

    for due_id, amount in selection.items():
        due = Due.objects.get(pk=due_id, student=student)
        value = Decimal(amount)
        due.paid = due.paid + value
        due.save()
        PaymentItem.objects.create(payment=payment, due=due, amount=value)

    request.session.pop("selection", None)
    request.session.pop("method", None)
    request.session.pop("phone", None)
    return redirect("payment_success", reference=payment.reference)


@login_required
def payment_success(request, reference):
    payment = get_object_or_404(Payment, reference=reference, student__user=request.user)
    return render(request, "portal/success.html", {"payment": payment})


@login_required
def receipt(request, reference):
    payment = get_object_or_404(Payment, reference=reference, student__user=request.user)
    return _render_receipt(request, payment)


def _render_receipt(request, payment):
    verify_url = request.build_absolute_uri(f"/verify/{payment.receipt_no.replace('/', '-')}/")
    return render(
        request,
        "portal/receipt.html",
        {
            "payment": payment,
            "student": payment.student,
            "verify_url": verify_url,
            "qr": qr_data_uri(f"{verify_url}?sig={payment.signature}"),
        },
    )


def verify_receipt(request, code):
    """Public page anyone (ICT / SRC desk) can use to confirm a receipt is genuine."""
    receipt_no = code.replace("-", "/")
    payment = Payment.objects.filter(receipt_no=receipt_no).first()
    supplied = request.GET.get("sig", "")
    genuine = bool(payment) and payment.is_authentic and (
        not supplied or supplied.upper() == payment.signature
    )
    return render(
        request,
        "portal/verify.html",
        {"payment": payment, "genuine": genuine, "code": receipt_no},
    )


@login_required
def payment_history(request):
    student = _student(request)
    return render(
        request,
        "portal/history.html",
        {"student": student, "payments": student.payments.all(), "active": "history"},
    )
