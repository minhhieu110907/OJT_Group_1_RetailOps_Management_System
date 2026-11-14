"""Supplier phone validation and E.164 normalization tests."""

import pytest
from pydantic import ValidationError

from app.modules.suppliers.schemas import SupplierCreate, SupplierUpdate


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        ("+84 912-345-678", "+84912345678"),
        ("0912 345 678", "+84912345678"),
        ("090-555-6666", "+84905556666"),
        ("+1 415 555 2671", "+14155552671"),
        ("+1 416 555 0123", "+14165550123"),
        ("+84          (912)          345          678", "+84912345678"),
    ],
)
def test_supplier_create_normalizes_valid_numbers_to_e164(
    phone: str, expected: str
) -> None:
    supplier = SupplierCreate(name="Valid Supplier", contact_phone=phone)

    assert supplier.contact_phone == expected


@pytest.mark.parametrize(
    "phone",
    [
        "12345",
        "091234567890123456",
        "+999123456789",
        "0912ABC678",
        "０９１２３４５６７８",
        "0912345678 ext. 12",
        "0912345678 x12",
        "1" * 65,
    ],
)
def test_supplier_create_rejects_invalid_or_unsupported_phone_input(
    phone: str,
) -> None:
    with pytest.raises(ValidationError):
        SupplierCreate(name="Invalid Supplier", contact_phone=phone)


def test_foreign_national_number_without_plus_is_not_guessed() -> None:
    with pytest.raises(ValidationError):
        SupplierCreate(name="Foreign Supplier", contact_phone="4155552671")


@pytest.mark.parametrize("phone", [None, "", "   "])
def test_optional_empty_phone_normalizes_to_none(phone: str | None) -> None:
    supplier = SupplierCreate(name="Optional Phone Supplier", contact_phone=phone)

    assert supplier.contact_phone is None


def test_supplier_update_preserves_omission_and_supports_explicit_clear() -> None:
    omitted = SupplierUpdate(name="Renamed Supplier")
    cleared = SupplierUpdate(contact_phone=None)

    assert "contact_phone" not in omitted.model_fields_set
    assert "contact_phone" in cleared.model_fields_set
    assert cleared.contact_phone is None
