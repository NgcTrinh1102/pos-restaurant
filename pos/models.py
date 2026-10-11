from django.conf import settings
from django.db import models


class Category(models.Model):
    """Nhóm sản phẩm: Canh, Cá nướng, Bún, Đồ uống..."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    """Món ăn / đồ uống."""
    code = models.CharField(max_length=20, unique=True, editable=False, blank=True)
    name = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    price = models.PositiveIntegerField()          # đơn vị VND, số nguyên
    is_available = models.BooleanField(default=True)  # True = Còn hàng

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code:                           # mã sản phẩm tự sinh (BR_016)
            self.code = f"SP{self.pk:04d}"
            super().save(update_fields=["code"])

    def __str__(self):
        return f"{self.code} - {self.name}"


class Order(models.Model):
    """Đơn hàng."""

    class OrderType(models.TextChoices):
        DINE_IN = "dine_in", "Ăn tại chỗ"
        TAKE_AWAY = "take_away", "Mang đi"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_KITCHEN = "in_kitchen", "In kitchen"
        READY = "ready", "Ready to serve"
        COMPLETED = "completed", "Completed"
        DELETED = "deleted", "Deleted"

    order_type = models.CharField(max_length=10, choices=OrderType.choices)
    table_number = models.CharField(max_length=10, blank=True)  # bắt buộc khi ăn tại chỗ
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    is_paid = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def subtotal(self):
        return sum(item.line_total for item in self.items.all())

    @property
    def vat(self):
        return round(self.subtotal * 8 / 100)

    @property
    def total(self):
        return self.subtotal + self.vat

    def __str__(self):
        return f"Đơn #{self.pk}"


class OrderItem(models.Model):
    """Một dòng món trong đơn hàng."""
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveSmallIntegerField()
    unit_price = models.PositiveIntegerField()      # giá tại thời điểm gọi món
    note = models.CharField(max_length=200, blank=True)

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class Transaction(models.Model):
    """Giao dịch thanh toán."""

    class Method(models.TextChoices):
        CASH = "cash", "Tiền mặt"
        QR = "qr", "Mã QR"

    order = models.ForeignKey(Order, related_name="transactions", on_delete=models.PROTECT)
    method = models.CharField(max_length=5, choices=Method.choices)
    amount_paid = models.PositiveIntegerField()
    change_returned = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)