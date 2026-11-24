"""Default WhatsApp message templates (editable by the Admin afterwards)."""

PLACEHOLDERS = {
    "customer_name": "Customer full name",
    "reference": "Order reference (LND-...)",
    "drop_off_date": "Drop-off date",
    "pickup_date": "Expected pickup date",
    "total_quantity": "Number of clothes/items",
    "total": "Order total",
    "amount_paid": "Amount paid so far",
    "balance": "Outstanding balance",
    "business_name": "Business name",
    "business_phone": "Business phone number",
}

DEFAULT_TEMPLATES = {
    "ORDER_RECEIVED": {
        "en": (
            "Hello {customer_name}, we have received your laundry order {reference} "
            "({total_quantity} items).\n"
            "Total: {total}\nPaid: {amount_paid}\nBalance: {balance}\n"
            "Expected pickup date: {pickup_date}.\n"
            "Thank you for choosing {business_name}! Contact: {business_phone}"
        ),
        "rw": (
            "Muraho {customer_name}, twakiriye imyenda yanyu, nomero y'itumiza {reference} "
            "(ibintu {total_quantity}).\n"
            "Igiteranyo: {total}\nMwishyuye: {amount_paid}\nIbisigaye: {balance}\n"
            "Itariki yo kuza kuyifata: {pickup_date}.\n"
            "Murakoze guhitamo {business_name}! Tel: {business_phone}"
        ),
    },
    "ORDER_READY": {
        "en": (
            "Hello {customer_name}, your laundry order {reference} is ready for collection.\n"
            "Expected pickup date: {pickup_date}.\nOutstanding balance: {balance}.\n"
            "Thank you for choosing {business_name}! Contact: {business_phone}"
        ),
        "rw": (
            "Muraho {customer_name}, imyenda yanyu (itumiza {reference}) yamaze gutunganywa, "
            "mushobora kuza kuyifata.\n"
            "Itariki yo kuyifata: {pickup_date}.\nIbisigaye kwishyura: {balance}.\n"
            "Murakoze guhitamo {business_name}! Tel: {business_phone}"
        ),
    },
    "PICKUP_REMINDER": {
        "en": (
            "Hello {customer_name}, this is a reminder that your laundry order {reference} "
            "is expected to be picked up on {pickup_date}.\n"
            "Outstanding balance: {balance}.\n{business_name} - {business_phone}"
        ),
        "rw": (
            "Muraho {customer_name}, turabibutsa ko imyenda yanyu (itumiza {reference}) "
            "iteganyijwe gufatwa ku itariki ya {pickup_date}.\n"
            "Ibisigaye kwishyura: {balance}.\n{business_name} - {business_phone}"
        ),
    },
    "PAYMENT_REMINDER": {
        "en": (
            "Hello {customer_name}, this is a friendly reminder that your laundry order "
            "{reference} has an outstanding balance of {balance} (total {total}, paid {amount_paid}).\n"
            "Thank you! {business_name} - {business_phone}"
        ),
        "rw": (
            "Muraho {customer_name}, turabibutsa ko ku itumiza {reference} hasigaye kwishyura "
            "{balance} (igiteranyo {total}, mwishyuye {amount_paid}).\n"
            "Murakoze! {business_name} - {business_phone}"
        ),
    },
}
