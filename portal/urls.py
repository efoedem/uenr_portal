from django.contrib.auth import views as auth_views
from django.urls import path

from . import admin_views, views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),

    # Password reset by email
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="portal/password_reset.html",
            email_template_name="portal/password_reset_email.txt",
            subject_template_name="portal/password_reset_subject.txt",
            success_url="/password-reset/sent/",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(template_name="portal/password_reset_sent.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="portal/password_reset_confirm.html",
            success_url="/reset/done/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="portal/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),

    # Student area
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    path("pay/", views.select_dues, name="select_dues"),
    path("pay/method/", views.payment_method, name="payment_method"),
    path("pay/confirm/", views.confirm_payment, name="confirm_payment"),
    path("pay/success/<str:reference>/", views.payment_success, name="payment_success"),
    path("receipt/<str:reference>/", views.receipt, name="receipt"),
    path("history/", views.payment_history, name="payment_history"),
    path("verify/<str:code>/", views.verify_receipt, name="verify_receipt"),

    # Staff area
    path("manage/", admin_views.admin_dashboard, name="admin_dashboard"),
    path("manage/students/", admin_views.admin_students, name="admin_students"),
    path("manage/students/export/", admin_views.admin_students_export, name="admin_students_export"),
    path("manage/students/template/", admin_views.admin_students_template, name="admin_students_template"),
    path("manage/students/upload/", admin_views.admin_students_upload, name="admin_students_upload"),
    path("manage/students/<int:pk>/delete/", admin_views.admin_student_delete, name="admin_student_delete"),
    path("manage/dues/", admin_views.admin_dues, name="admin_dues"),
    path("manage/dues/<int:pk>/republish/", admin_views.admin_due_republish, name="admin_due_republish"),
    path("manage/dues/<int:pk>/delete/", admin_views.admin_due_delete, name="admin_due_delete"),
    path("manage/payments/", admin_views.admin_payments, name="admin_payments"),
    path("manage/payments/export/", admin_views.admin_payments_export, name="admin_payments_export"),
    path("manage/receipt/<str:reference>/", admin_views.admin_receipt, name="admin_receipt"),
]
