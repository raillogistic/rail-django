"""Filter policy extraction."""


def extract_filter_policies(model_cls) -> list[dict]:
    return [{"field": field.name, "operators": ["exact", "icontains"]} for field in model_cls._meta.fields]
