from django.contrib import admin

from .models import Due, DueTemplate, Payment, PaymentItem, Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_id", "full_name", "level", "programme", "phone")
    list_filter = ("level", "programme")
    search_fields = ("student_id", "user__first_name", "user__last_name")


@admin.register(DueTemplate)
class DueTemplateAdmin(admin.ModelAdmin):
    list_display = ("description", "amount", "level", "programme", "created_at")
    list_filter = ("level", "programme")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_no", "reference", "student", "amount", "method", "phone_number", "created_at")
    list_filter = ("method", "student__level", "student__programme")
    search_fields = ("receipt_no", "reference", "phone_number", "student__student_id")


admin.site.register([Due, PaymentItem])
admin.site.site_header = "UENR Payment Portal Administration"
