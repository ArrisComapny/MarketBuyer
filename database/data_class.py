from dataclasses import dataclass

@dataclass
class QrResult:
    phone10: str
    account_name: str
    adress_pvz: str
    quantity: int
    sku_product: str
    status: str
    code: str
    qr_base64: str
