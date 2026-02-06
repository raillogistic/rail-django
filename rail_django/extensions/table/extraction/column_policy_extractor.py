"""Column policy extraction for visibility/editability."""


def extract_column_policies(model_cls) -> list[dict]:
    return [
        {
            "name": field.name,
            "visible": True,
            "editable": not getattr(field, "primary_key", False),
        }
        for field in model_cls._meta.fields
    ]
