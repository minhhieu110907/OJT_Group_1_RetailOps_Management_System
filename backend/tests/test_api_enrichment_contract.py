"""Runtime/frozen OpenAPI parity for the API enrichment DTOs."""

from pathlib import Path

import yaml
from fastapi import FastAPI

from app.modules.auth.approval_router import router as approval_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.schemas import UserRead
from app.modules.categories.router import category_router
from app.modules.products.router import router as product_router
from app.modules.sales.router import router as sales_router


def _runtime_schemas() -> dict[str, object]:
    app = FastAPI()
    for router in (
        auth_router,
        approval_router,
        category_router,
        product_router,
        sales_router,
    ):
        app.include_router(router)
    schemas = app.openapi()["components"]["schemas"]
    schemas["UserRead"] = UserRead.model_json_schema()
    return schemas


def _frozen_schemas() -> dict[str, object]:
    path = Path(__file__).parents[2] / "contracts" / "openapi.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["components"]["schemas"]


def _constraint(property_schema: dict[str, object], name: str) -> object:
    if name in property_schema:
        return property_schema[name]
    for alternative in property_schema.get("anyOf", ()):
        if name in alternative:
            return alternative[name]
    raise AssertionError(f"Missing {name}: {property_schema}")


def test_changed_frozen_dtos_have_declared_required_properties() -> None:
    frozen = _frozen_schemas()
    for name in (
        "ProductCreateRequest",
        "ProductUpdateRequest",
        "ProductRead",
        "RegisterRequest",
        "CategoryRead",
        "UserRead",
        "AuthenticatedUser",
        "ApprovalListItemRead",
        "OrderRead",
    ):
        schema = frozen[name]
        assert set(schema.get("required", ())) <= set(schema["properties"]), name


def test_runtime_and_frozen_enrichment_required_nullable_semantics_match() -> None:
    runtime = _runtime_schemas()
    frozen = _frozen_schemas()
    response_fields = {
        "ProductRead": "image_url",
        "CategoryRead": "product_count",
        "UserRead": "full_name",
        "AuthenticatedUser": "full_name",
        "ApprovalListItemRead": "full_name",
        "OrderRead": "created_by_name",
    }
    for schema_name, field_name in response_fields.items():
        assert field_name in runtime[schema_name]["required"]
        assert field_name in frozen[schema_name]["required"]
        assert field_name in runtime[schema_name]["properties"]
        assert field_name in frozen[schema_name]["properties"]

    for source in (runtime, frozen):
        assert "cancelled_by_name" in source["OrderRead"]["required"]
        assert source["CategoryRead"]["properties"]["product_count"]["minimum"] == 0


def test_runtime_and_frozen_request_enrichment_constraints_match() -> None:
    runtime = _runtime_schemas()
    frozen = _frozen_schemas()
    for schema_name in ("ProductCreateRequest", "ProductUpdateRequest"):
        for source in (runtime, frozen):
            image = source[schema_name]["properties"]["image_url"]
            assert _constraint(image, "maxLength") == 500
            assert _constraint(image, "pattern") == "^https://"
        assert "image_url" not in runtime[schema_name].get("required", ())
        assert "image_url" not in frozen[schema_name].get("required", ())

    for source in (runtime, frozen):
        full_name = source["RegisterRequest"]["properties"]["full_name"]
        assert _constraint(full_name, "minLength") == 1
        assert _constraint(full_name, "maxLength") == 120
        assert "full_name" not in source["RegisterRequest"].get("required", ())
