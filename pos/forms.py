from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    price = forms.IntegerField(
        label="Giá (VNĐ)", min_value=1, max_value=100_000_000,
        widget=forms.NumberInput(attrs={"placeholder": "Ví dụ: 59000", "step": 1, "min": 0}),
    )

    class Meta:
        model = Product
        fields = ["name", "category", "price", "is_available", "image"]
        labels = {
            "name": "Tên món",
            "category": "Nhóm món",
            "is_available": "Còn hàng (cho phép gọi món)",
            "image": "Ảnh món",
        }
        error_messages = {
            "name": {"unique": "Tên món này đã tồn tại. Vui lòng đặt tên khác."},
        }
