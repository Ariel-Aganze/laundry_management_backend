"""
Receipt PDF rendering with ReportLab.

Thermal receipts (58mm / 80mm) are one continuous page whose height fits the
content. A4 receipts use the same single-column layout and paginate.
"""

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from apps.common.i18n import format_date, format_datetime, format_money, label, normalize_language

# paper -> (page width, side margin, base font size)
PAPERS = {
    "58mm": (58 * mm, 3 * mm, 7.0),
    "80mm": (80 * mm, 4 * mm, 8.0),
    "A4": (A4[0], 20 * mm, 10.0),
}
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


class _Layout:
    """Collects drawing operations so the total height is known before drawing."""

    def __init__(self, width, base_size):
        self.width = width
        self.base = base_size
        self.ops = []

    @staticmethod
    def _font(bold):
        return FONT_BOLD if bold else FONT

    def text(self, value, *, align="left", bold=False, scale=1.0):
        size = self.base * scale
        font = self._font(bold)
        for line in simpleSplit(str(value or ""), font, size, self.width) or [""]:
            self.ops.append(("text", size * 1.35, line, align, font, size))

    def pair(self, left, right, *, bold=False, scale=1.0):
        size = self.base * scale
        font = self._font(bold)
        left, right = str(left or ""), str(right or "")
        gap = size * 0.8
        right_width = stringWidth(right, font, size)
        available = self.width - right_width - gap
        if available < self.width * 0.35:
            # Not enough room on one line: label above, value right-aligned below.
            self.text(left, bold=bold, scale=scale)
            self.ops.append(("text", size * 1.35, right, "right", font, size))
            return
        lines = simpleSplit(left, font, size, available) or [""]
        self.ops.append(("pair", size * 1.35, lines[0], right, font, size))
        for line in lines[1:]:
            self.ops.append(("text", size * 1.35, line, "left", font, size))

    def rule(self):
        self.ops.append(("rule", self.base * 1.1))

    def space(self, height):
        self.ops.append(("space", height))

    def image(self, reader, width, height):
        self.ops.append(("image", height + self.base * 0.6, reader, width, height))

    @property
    def height(self):
        return sum(op[1] for op in self.ops)


def _draw_op(c, op, x, y_top, width):
    kind = op[0]
    height = op[1]
    if kind == "text":
        _, _, line, align, font, size = op
        c.setFont(font, size)
        baseline = y_top - size
        if align == "center":
            c.drawCentredString(x + width / 2, baseline, line)
        elif align == "right":
            c.drawRightString(x + width, baseline, line)
        else:
            c.drawString(x, baseline, line)
    elif kind == "pair":
        _, _, left, right, font, size = op
        c.setFont(font, size)
        baseline = y_top - size
        c.drawString(x, baseline, left)
        c.drawRightString(x + width, baseline, right)
    elif kind == "rule":
        c.saveState()
        c.setDash(1, 2)
        c.setLineWidth(0.5)
        middle = y_top - height / 2
        c.line(x, middle, x + width, middle)
        c.restoreState()
    elif kind == "image":
        _, _, reader, img_w, img_h = op
        c.drawImage(reader, x + (width - img_w) / 2, y_top - img_h, img_w, img_h, mask="auto")


def _logo_reader(max_width, max_height):
    from apps.business.models import BusinessSettings

    business = BusinessSettings.load()
    if not (business.receipt_show_logo and business.logo_data):
        return None
    try:
        reader = ImageReader(BytesIO(bytes(business.logo_data)))
        img_w, img_h = reader.getSize()
        ratio = min(max_width / img_w, max_height / img_h)
        return reader, img_w * ratio, img_h * ratio
    except Exception:  # A broken logo must never block a receipt.
        return None


def _build(layout, data, lang):
    business = data.get("business", {})
    currency = business.get("currency", "RWF")
    decimals = business.get("currency_decimals", 0)

    def money(value):
        return format_money(value, currency, decimals)

    logo = _logo_reader(layout.width * 0.6, 22 * mm)
    if logo:
        layout.image(*logo)
    layout.text(business.get("name"), align="center", bold=True, scale=1.35)
    for line in (business.get("address"), business.get("phone") and f"{label('tel', lang)}: {business['phone']}",
                 business.get("email")):
        if line:
            layout.text(line, align="center", scale=0.9)
    layout.rule()

    is_payment = data.get("receipt_type") == "PAYMENT"
    layout.text(label("payment_receipt" if is_payment else "order_receipt", lang), align="center", bold=True,
                scale=1.15)
    layout.pair(label("receipt_no", lang), data.get("receipt_number"))
    layout.pair(label("order_ref", lang), data["order"]["reference"], bold=True)
    layout.pair(label("date", lang), format_datetime(data.get("generated_at"), lang))
    layout.pair(label("cashier", lang), data.get("generated_by"))
    layout.rule()

    layout.pair(label("customer", lang), data["customer"]["name"])
    layout.pair(label("phone", lang), data["customer"]["phone"])
    layout.pair(label("drop_off", lang), format_date(data["order"]["drop_off_date"], lang))
    layout.pair(label("pickup", lang), format_date(data["order"]["pickup_date"], lang), bold=True)
    layout.rule()

    for item in data.get("items", []):
        layout.text(f"{item['item']} - {item['category']}", bold=True)
        layout.pair(
            f"{item['quantity']} x {money(item['unit_price'])} ({label(item['service_type'], lang)})",
            money(item["subtotal"]),
        )
        if item.get("condition_notes"):
            layout.text(f"{label('notes', lang)}: {item['condition_notes']}", scale=0.88)
        layout.space(layout.base * 0.3)
    layout.rule()

    layout.pair(label("total_items", lang), data.get("total_quantity"))
    layout.pair(label("total", lang), money(data.get("total_amount")), bold=True, scale=1.15)
    layout.pair(label("paid", lang), money(data.get("amount_paid")))
    layout.pair(label("balance", lang), money(data.get("balance")), bold=True, scale=1.1)
    layout.pair(label("payment_status", lang), label(data.get("payment_status"), lang))

    payment = data.get("payment")
    if payment:
        layout.rule()
        layout.text(label("this_payment", lang), bold=True)
        layout.pair(label("amount", lang), money(payment["amount"]), bold=True)
        method = payment.get("method_other") or label(payment.get("payment_method"), lang)
        layout.pair(label("method", lang), method)
        if payment.get("transaction_reference"):
            layout.pair(label("reference", lang), payment["transaction_reference"])
        layout.pair(label("received_at", lang), format_datetime(payment.get("received_at"), lang))

    layout.rule()
    if business.get("footer"):
        layout.text(business["footer"], align="center", scale=0.92)
    layout.text(label("thank_you", lang), align="center", bold=True)


def render_receipt_pdf(data, paper="80mm", lang="en"):
    paper = paper if paper in PAPERS else "80mm"
    lang = normalize_language(lang)
    page_width, margin, base = PAPERS[paper]
    content_width = page_width - 2 * margin

    layout = _Layout(content_width, base)
    _build(layout, data, lang)

    buffer = BytesIO()
    if paper == "A4":
        page_height = A4[1]
        c = canvas.Canvas(buffer, pagesize=A4)
        y = page_height - margin
        for op in layout.ops:
            if y - op[1] < margin:
                c.showPage()
                y = page_height - margin
            _draw_op(c, op, margin, y, content_width)
            y -= op[1]
    else:
        page_height = max(layout.height + 2 * margin, 60 * mm)
        c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
        y = page_height - margin
        for op in layout.ops:
            _draw_op(c, op, margin, y, content_width)
            y -= op[1]

    c.setTitle(f"{data.get('receipt_number', 'receipt')}")
    c.showPage()
    c.save()
    return buffer.getvalue()
