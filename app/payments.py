from decimal import Decimal
from typing import Any
from uuid import uuid4

from anyio import to_thread
from yookassa import Configuration, Payment

from app.config import (
    YOOKASSA_RETURN_URL,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_SHOP_ID,
)


async def create_yookassa_payment(
    *,
    order_id: int,
    amount: Decimal,
    user_email: str,
    description: str,
) -> dict[str, Any]:
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise RuntimeError("Задайте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в .env")

    Configuration.account_id = YOOKASSA_SHOP_ID,
    Configuration.secret_key = YOOKASSA_SECRET_KEY

    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL,
        },
        "capture": True,
        "description": description,
        "metadata": {
            "order_id": order_id,
        },
        "receipt": {
            "customer": {
                "email": user_email,
            },
            "items": [
                {
                    "description": description[:128],
                    "quantity": "1.00",
                    "amount": {
                        "value": f"{amount:.2f}",
                        "currency": "RUB",
                    },
                    "vat_code": 1,
                    "payment_mode": "full_prepayment",
                    "payment_subject": "commodity",
                }
            ]
        }
    }

    def _request() -> Payment:
        # send POST to /v3/payments
        return Payment.create(payload, str(uuid4()))

    payment: Payment = await to_thread.run_sync(_request)
    confirmation_url = getattr(payment.confirmation, "confirmation", None)
    return {
        "id": payment.id,
        "status": payment.status,
        "confirmation_url": confirmation_url
    }