from dataclasses import dataclass

@dataclass(slots=True)
class SelectedCounts:
    total_all: int = 0
    total_selected: int = 0
    disable: int = 0
    login: int = 0
    logout: int = 0


@dataclass(slots=True)
class RowItems:
    row_idx: int
    phone10: str
    status: str

@dataclass
class QrItems:
    sku: str
    quantity: int
    status: str

@dataclass
class QrPVZ:
    address_pvz: str
    products: list[QrItems]

@dataclass
class QrResult:
    phone10: str
    account_name: str
    pvz_list: list[QrPVZ]
    code: str
    qr_base64: str