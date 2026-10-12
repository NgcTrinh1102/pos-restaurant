from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.db import transaction
from django.db.models import F, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ProductForm
from .models import Order, OrderItem, Product, Transaction


@login_required
def product_list(request):
    products = Product.objects.select_related("category").order_by("category__name", "name")
    return render(request, "pos/product_list.html", {"products": products})


def staff_required(view):
    """Chỉ nhân viên quản lý (is_staff) mới được thêm/sửa/xóa món."""
    return login_required(user_passes_test(lambda u: u.is_staff, login_url="product_list")(view))


@staff_required
def product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        messages.success(request, f"Đã thêm món {product.name}.")
        return redirect("product_list")
    return render(request, "pos/product_form.html", {"form": form, "product": None})


@staff_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Đã cập nhật món {product.name}.")
        return redirect("product_list")
    return render(request, "pos/product_form.html", {"form": form, "product": product})


@staff_required
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    # Món đã từng được gọi thì giữ lại để không mất lịch sử đơn hàng
    if OrderItem.objects.filter(product=product).exists():
        messages.error(
            request,
            f"Không thể xóa {product.name} vì đã có trong đơn hàng. Hãy sửa món và bỏ chọn 'Còn hàng'.",
        )
    else:
        name = product.name
        product.delete()
        messages.success(request, f"Đã xóa món {name}.")
    return redirect("product_list")


@login_required
def order_create(request):
    # Chỉ cho gọi những món đang "Còn hàng" (BR_006)
    products = (
        Product.objects.filter(is_available=True)
        .select_related("category")
        .order_by("category__name", "name")
    )

    quantities = {}       # {mã món: số lượng} để giữ lại giỏ hàng khi có lỗi
    posted_type = ""
    posted_table = ""

    if request.method == "POST":
        order_type = request.POST.get("order_type", "")
        table_number = request.POST.get("table_number", "").strip()
        posted_type, posted_table = order_type, table_number

        # Đọc số lượng của từng món từ form
        selected = []
        errors = []
        for p in products:
            raw = request.POST.get(f"qty_{p.id}", "0")
            try:
                qty = int(raw)
            except ValueError:
                qty = 0
            if qty > 0:
                quantities[p.id] = min(qty, 999)
            if qty > 999:
                errors.append(f"Số lượng món {p.name} tối đa là 999.")
            elif qty > 0:
                selected.append((p, qty))

        # Kiểm tra dữ liệu (validation)
        if order_type not in (Order.OrderType.DINE_IN, Order.OrderType.TAKE_AWAY):
            errors.append("Vui lòng chọn loại đơn hàng.")
        if order_type == Order.OrderType.DINE_IN and not table_number:
            errors.append("Đơn ăn tại chỗ cần nhập số bàn.")
        if not selected:
            errors.append("Vui lòng chọn ít nhất một món.")

        if errors:
            return render(
                request,
                "pos/order_create.html",
                {
                    "products": products,
                    "errors": errors,
                    "quantities": quantities,
                    "posted_type": posted_type,
                    "posted_table": posted_table,
                },
            )

        # Lưu đơn hàng và các dòng món trong một khối
        with transaction.atomic():
            order = Order.objects.create(
                order_type=order_type,
                table_number=table_number if order_type == Order.OrderType.DINE_IN else "",
                created_by=request.user,
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(order=order, product=p, quantity=qty, unit_price=p.price)
                    for p, qty in selected
                ]
            )
        messages.success(request, f"Đơn hàng #{order.pk} đã được đặt thành công.")
        return redirect("order_list")

    return render(
        request,
        "pos/order_create.html",
        {
            "products": products,
            "quantities": quantities,
            "posted_type": posted_type,
            "posted_table": posted_table,
        },
    )


@login_required
def order_list(request):
    current = request.GET.get("status", "")
    groups = {
        "cooking": [Order.Status.PENDING, Order.Status.IN_KITCHEN],
        "done": [Order.Status.READY, Order.Status.COMPLETED],
        "cancelled": [Order.Status.DELETED],
    }
    orders = Order.objects.prefetch_related("items__product").order_by("-created_at")
    if current in groups:
        orders = orders.filter(status__in=groups[current])
    else:
        current = ""
    return render(request, "pos/order_list.html", {"orders": orders, "current": current})


@login_required
@require_POST
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk)
    # Chỉ hủy được đơn đang Pending và chưa thanh toán (BR_012)
    if order.status == Order.Status.PENDING and not order.is_paid:
        order.status = Order.Status.DELETED
        order.save()
        messages.success(request, f"Đơn hàng #{order.pk} đã được hủy.")
    return redirect("order_list")


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    items = order.items.select_related("product")
    return render(request, "pos/order_detail.html", {"order": order, "items": items})


@login_required
def order_pay_cash(request, pk):
    """Trang thanh toán: tiền mặt (bàn phím số) hoặc QR (mô phỏng)."""
    order = get_object_or_404(Order, pk=pk)

    # Đơn đã thanh toán hoặc đã hủy thì không thanh toán nữa
    if order.is_paid or order.status == Order.Status.DELETED:
        return redirect("order_detail", pk=order.pk)

    error = None
    if request.method == "POST":
        method = request.POST.get("method", "cash")
        if method == "qr":
            # Mô phỏng: nhân viên xác nhận đã nhận tiền chuyển khoản
            amount_paid, change = order.total, 0
            method_value = getattr(Transaction.Method, "QR", "qr")
        else:
            method_value = Transaction.Method.CASH
            raw = request.POST.get("amount_paid", "").strip()
            try:
                amount_paid = int(raw)
            except ValueError:
                amount_paid = None
            if amount_paid is None or amount_paid < 0:
                error = "Vui lòng nhập số tiền hợp lệ."
            elif amount_paid < order.total:
                error = "Số tiền khách đưa chưa đủ. Vui lòng yêu cầu khách trả thêm."
            else:
                change = amount_paid - order.total

        if error is None:
            with transaction.atomic():
                Transaction.objects.create(
                    order=order,
                    method=method_value,
                    amount_paid=amount_paid,
                    change_returned=change,
                )
                order.is_paid = True
                order.status = Order.Status.COMPLETED
                order.save()
            return redirect("order_paid", pk=order.pk)

    items = order.items.select_related("product")
    return render(
        request,
        "pos/order_pay_cash.html",
        {"order": order, "items": items, "error": error},
    )


@login_required
def order_paid(request, pk):
    """Màn hình thanh toán thành công."""
    order = get_object_or_404(Order, pk=pk)
    txn = order.transactions.order_by("-created_at").first()
    if not order.is_paid or txn is None:
        return redirect("order_detail", pk=order.pk)
    return render(request, "pos/order_paid.html", {"order": order, "txn": txn})


@login_required
@permission_required("pos.view_transaction", raise_exception=True)
def revenue_report(request):
    today = timezone.localdate()
    error = None

    # Khoảng thời gian: hôm nay / 7 ngày / 30 ngày / ngày tự chọn
    range_key = request.GET.get("range", "today")
    days_map = {"today": 1, "7d": 7, "30d": 30}
    raw = request.GET.get("date", "")

    if raw:
        try:
            start = end = date.fromisoformat(raw)
        except ValueError:
            start = end = today
            error = "Ngày không hợp lệ."
        range_key = "custom"
    else:
        if range_key not in days_map:
            range_key = "today"
        end = today
        start = today - timedelta(days=days_map[range_key] - 1)

    # Không cho xem ngày trong tương lai
    if end > today:
        start = end = today
        error = "Không thể xem báo cáo của ngày trong tương lai."

    transactions = Transaction.objects.filter(
        created_at__date__gte=start, created_at__date__lte=end
    )

    # Tiền thực thu = tiền khách đưa - tiền thừa trả lại
    real_amount = F("amount_paid") - F("change_returned")
    total_revenue = transactions.aggregate(s=Sum(real_amount))["s"] or 0
    cash_revenue = (
        transactions.filter(method=Transaction.Method.CASH)
        .aggregate(s=Sum(real_amount))["s"]
        or 0
    )
    qr_revenue = total_revenue - cash_revenue
    total_orders = transactions.values("order").distinct().count()
    average = round(total_revenue / total_orders) if total_orders else 0

    # Doanh thu theo từng ngày (cho biểu đồ cột), ngày không có đơn = 0
    per_day = {
        row["d"]: row["s"] or 0
        for row in transactions.annotate(d=TruncDate("created_at"))
        .values("d")
        .annotate(s=Sum(real_amount))
    }
    labels, values = [], []
    d = start
    while d <= end:
        labels.append(d.strftime("%d/%m"))
        values.append(per_day.get(d, 0))
        d += timedelta(days=1)

    # 5 món bán chạy nhất trong khoảng thời gian
    top_products = list(
        OrderItem.objects.filter(
            order__transactions__created_at__date__gte=start,
            order__transactions__created_at__date__lte=end,
        )
        .values("product__name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")[:5]
    )

    context = {
        "range_key": range_key,
        "start": start,
        "end": end,
        "selected": end.isoformat() if range_key == "custom" else "",
        "today": today.isoformat(),
        "error": error,
        "total_revenue": total_revenue,
        "cash_revenue": cash_revenue,
        "qr_revenue": qr_revenue,
        "total_orders": total_orders,
        "average": average,
        "top_products": top_products,
        "chart": {
            "labels": labels,
            "values": values,
            "top_labels": [p["product__name"] for p in top_products],
            "top_values": [p["qty"] for p in top_products],
            "cash": cash_revenue,
            "qr": qr_revenue,
        },
    }
    return render(request, "pos/revenue_report.html", context)
