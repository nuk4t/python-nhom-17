from django.contrib import admin
from .models import Customer, Room, Booking

# Thay đổi tiêu đề trang Admin cho chuyên nghiệp
admin.site.site_header = "Hệ Thống Quản Lý Khách Sạn"
admin.site.site_title = "Admin Khách Sạn"

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'cccd')
    search_fields = ('full_name', 'phone')

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'room_type', 'price_per_night', 'is_available')
    list_filter = ('room_type', 'is_available')
    search_fields = ('room_number',)

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('customer', 'room', 'check_in', 'check_out', 'is_paid')
    list_filter = ('is_paid', 'check_in')
    date_hierarchy = 'check_in'