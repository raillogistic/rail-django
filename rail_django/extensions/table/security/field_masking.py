"""Field-level masking utilities."""


def mask_value(value: object, mask: str = "***") -> object:
    if value in (None, ""):
        return value
    return mask


def apply_field_masking(row: dict, masked_fields: set[str]) -> dict:
    return {key: (mask_value(value) if key in masked_fields else value) for key, value in row.items()}
