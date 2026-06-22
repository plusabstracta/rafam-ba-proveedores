from decimal import Decimal

import pytest

from src.validation import (
    DECIMAL_MAX_ABS,
    validate_amount,
    validate_date_only,
    validate_required_fk,
)


class TestValidateAmount:
    def test_accepts_normal_value_rounded(self):
        result = validate_amount("1234.567")
        assert result.ok
        assert result.value == 1234.57

    def test_accepts_comma_decimal_separator(self):
        result = validate_amount("10,50")
        assert result.ok
        assert result.value == 10.50

    def test_rejects_negative_by_default(self):
        result = validate_amount("-5.00", field="importe_total")
        assert not result.ok
        assert "negativo" in result.reason

    def test_allows_negative_when_flagged(self):
        result = validate_amount("-5.00", allow_negative=True)
        assert result.ok
        assert result.value == -5.0

    def test_rejects_zero_when_not_allowed(self):
        result = validate_amount("0", allow_zero=False)
        assert not result.ok
        assert "cero" in result.reason

    def test_rejects_overflow_decimal_14_2(self):
        overflow = DECIMAL_MAX_ABS + Decimal("1")
        result = validate_amount(str(overflow))
        assert not result.ok
        assert "DECIMAL(14,2)" in result.reason

    def test_accepts_max_boundary(self):
        result = validate_amount(str(DECIMAL_MAX_ABS))
        assert result.ok

    def test_rejects_non_numeric(self):
        result = validate_amount("abc")
        assert not result.ok
        assert "no parseable" in result.reason

    def test_required_empty_rejected(self):
        result = validate_amount(None, required=True)
        assert not result.ok

    def test_optional_empty_accepted_as_none(self):
        result = validate_amount(None, required=False)
        assert result.ok
        assert result.value is None


class TestValidateRequiredFk:
    def test_accepts_positive_int(self):
        result = validate_required_fk(42, field="proveedor_id")
        assert result.ok
        assert result.value == 42

    def test_accepts_numeric_string(self):
        result = validate_required_fk("7", field="pedido_id")
        assert result.ok
        assert result.value == 7

    def test_rejects_none(self):
        result = validate_required_fk(None, field="proveedor_id")
        assert not result.ok
        assert "ausente" in result.reason

    def test_rejects_zero_or_negative(self):
        assert not validate_required_fk(0, field="proveedor_id").ok
        assert not validate_required_fk(-1, field="proveedor_id").ok

    def test_rejects_non_numeric(self):
        result = validate_required_fk("xx", field="proveedor_id")
        assert not result.ok


class TestValidateDateOnly:
    def test_accepts_iso_date(self):
        result = validate_date_only("2026-01-15")
        assert result.ok
        assert result.value == "2026-01-15"

    def test_strips_time_component(self):
        result = validate_date_only("2026-01-15 00:00:00")
        assert result.ok
        assert result.value == "2026-01-15"

    def test_rejects_bad_format(self):
        result = validate_date_only("15/01/2026")
        assert not result.ok
        assert "formato" in result.reason

    def test_optional_empty_accepted(self):
        result = validate_date_only(None, required=False)
        assert result.ok
        assert result.value is None

    def test_required_empty_rejected(self):
        result = validate_date_only("", required=True)
        assert not result.ok
