from django.db import models
from django.utils import timezone

class Customer(models.Model):
    full_name = models.CharField(max_length=100, verbose_name="Họ và tên")
    phone = models.CharField(max_length=15, unique=True, verbose_name="Số điện thoại")
    cccd = models.CharField(max_length=20, blank=True, null=True, verbose_name="Số CCCD/CMND")

    def __str__(self):
        return self.full_name

class Room(models.Model):
    ROOM_TYPES = (
        ('STANDARD', 'Phòng Thường'),
        ('DELUXE', 'Phòng Cao cấp'),
        ('VIP', 'Phòng VIP'),
    )
    room_number = models.CharField(max_length=10, unique=True, verbose_name="Số phòng")
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default='STANDARD', verbose_name="Loại phòng")
    price_per_night = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Giá 1 đêm (VNĐ)")
    is_available = models.BooleanField(default=True, verbose_name="Đang trống")

    def __str__(self):
        return f"Phòng {self.room_number} ({self.get_room_type_display()})"

class Booking(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, verbose_name="Khách hàng")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, verbose_name="Phòng")
    check_in = models.DateField(default=timezone.now, verbose_name="Ngày nhận phòng")
    check_out = models.DateField(verbose_name="Ngày trả phòng")
    is_paid = models.BooleanField(default=False, verbose_name="Trạng thái thanh toán")

    def __str__(self):
        return f"{self.customer.full_name} - {self.room.room_number}"