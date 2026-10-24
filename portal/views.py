from decimal import Decimal, InvalidOperation
import logging
import time

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .models import LEVELS, PAYMENT_METHODS, PROGRAMMES, Due, DueTemplate, Payment, PaymentItem, Student
from .utils import qr_data_uri

# --- Security logging ---------------------------------------------------------
# Structured audit trail for security-relevant events. Configure the
# "portal.audit" logger in settings.LOGGING to ship these to files/monitoring.
audit_log = logging.getLogger("portal.audit")


def _audit(request, event, **details):
    """Record a security-relevant event with actor, IP and details."""
    ip = request.META.get("REMOTE_ADDR", "")
    actor = getattr(getattr(request, "user", None), "username", "") or "anonymous"
    payload = " ".join(f"{k}={v}" for k, v in details.items())
    audit_log.info("event=%s actor=%s ip=%s %s", event, actor, ip, payload)


# --- Login rate limiting ------------------------------------------------------
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5 minutes
LOGIN_LOCKOUT_SECONDS = 900  # 15 minutes


def _client_ip(request):
    return request.META.get("REMOTE_ADDR", "unknown")


def _login_blocked(request, student_id):
    """Return True if this client/IP+account is temporarily locked out."""
    ip = _client_ip(request)
    key = f"login-fail:{ip}:{student_id.lower()}"
    data = cache.get(key)
    return bool(data and data.get("count", 0) >= LOGIN_MAX_ATTEMPTS and
                data.get("locked_until", 0) > time.time())


def _record_login_failure(request, student_id):
    ip = _client_ip(request)
    key = f"login-fail:{ip}:{student_id.lower()}"
    data = cache.get(key) or {"count": 0, "locked_until": 0}
    data["count"] += 1
    if data["count"] >= LOGIN_MAX_ATTEMPTS:
        data["locked_until"] = time.time() + LOGIN_LOCKOUT_SECONDS
        data["count"] = 0  # restart counting after the lockout expires
    cache.set(key, data, LOGIN_WINDOW_SECONDS + LOGIN_LOCKOUT_SECONDS)
    _audit(request, "login_failed", student_id=student_id,
           attempts=data["count"])


def _clear_login_failures(request, student_id):
    cache.delete(f"login-fail:{_client_ip(request)}:{student_id.lower()}")


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
        if student_id and _login_blocked(request, student_id):
            messages.error(
                request,
                "Too many failed attempts. Try again in 15 minutes.",
            )
            _audit(request, "login_blocked", student_id=student_id)
        else:
            user = authenticate(request, username=student_id, password=password)
            if user is not None:
                _clear_login_failures(request, student_id)
                login(request, user)
                _audit(request, "login_success")
                if user.is_staff:
                    return redirect("admin_dashboard")
                return redirect("dashboard")
            _record_login_failure(request, student_id)
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
            _audit(request, "signup", student_id=student_id)
            messages.success(request, "Account created. Welcome to the portal!")
            return redirect("dashboard")
    return render(
        request,
        "portal/signup.html",
        {"programmes": PROGRAMMES, "levels": LEVELS},
    )


def logout_view(request):
    _audit(request, "logout")
    logout(request)
    return redirect("landing")


@login_required
def dashboard(request):
    student = _student(request)
    dues = student.dues.select_related("template")
    return render(
        request,
        "portal/dashboard.html",
        {"student": student, "dues": dues, "active": "dashboard"},
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
    """Simulated payment processing: marks dues paid and creates a signed receipt.

    Runs inside a single database transaction so a mid-loop failure cannot
    leave dues marked paid without a matching payment record (or vice versa).
    An idempotency guard prevents double-submits from creating duplicates.
    """
    student = _student(request)
    selection = request.session.get("selection")
    method = request.session.get("method")
    if not selection or not method:
        return redirect("select_dues")

    # Idempotency: if this session already completed this exact selection,
    # redirect to the existing receipt instead of creating a duplicate.
    last_ref = request.session.get("last_payment_ref")
    if last_ref:
        existing = Payment.objects.filter(
            reference=last_ref, student=student,
        ).first()
        if existing:
            request.session.pop("selection", None)
            request.session.pop("method", None)
            request.session.pop("phone", None)
            return redirect("payment_success", reference=existing.reference)

    total = sum(Decimal(v) for v in selection.values())
    with transaction.atomic():
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
            # Lock the due row so concurrent submissions cannot overpay.
            due = Due.objects.select_for_update().get(pk=due_id, student=student)
            value = min(Decimal(amount), due.balance)
            if value <= 0:
                continue
            due.paid = due.paid + value
            due.save()
            PaymentItem.objects.create(payment=payment, due=due, amount=value)

    request.session["last_payment_ref"] = reference
    request.session.pop("selection", None)
    request.session.pop("method", None)
    request.session.pop("phone", None)
    _audit(request, "payment_recorded", reference=reference, amount=str(total), method=method)
    return redirect("payment_success", reference=payment.reference)


@login_required
def payment_success(request, reference):
    payment = get_object_or_404(Payment, reference=reference, student__user=request.user)
    # Clear the idempotency marker once the student has seen the receipt.
    if request.session.get("last_payment_ref") == reference:
        request.session.pop("last_payment_ref", None)
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
    if payment and not genuine:
        _audit(request, "receipt_verification_failed", receipt_no=receipt_no)
    return render(
        request,
        "portal/verify.html",
        {"payment": payment, "genuine": genuine, "code": receipt_no},
    )


@login_required
def payment_history(request):
    student = _student(request)
    payments = student.payments.select_related("student", "student__user")
    return render(
        request,
        "portal/history.html",
        {"student": student, "payments": payments, "active": "history"},
    )
