"""Keep integer validation bounds exact through FastAPI's float-valued OpenAPI Schema model."""
from __future__ import annotations

from fastapi.routing import APIRoute
from pydantic import BaseModel

BOUNDS = (("minimum", "ge"), ("maximum", "le"), ("exclusiveMinimum", "gt"), ("exclusiveMaximum", "lt"))
BOUND_NAMES = {name for name, _ in BOUNDS}


def _integer_format(schema):
    if schema.get("type") == "integer" and schema.get("maximum", 0) > (1 << 31)-1:
        schema["format"] = "int64"


def _restore(target, source):
    if isinstance(target, dict) and isinstance(source, dict):
        for key, value in source.items():
            if key in BOUND_NAMES and type(value) is int:
                target[key] = value
            elif key in target:
                _restore(target[key], value)
        _integer_format(target)
    elif isinstance(target, list) and isinstance(source, list):
        for t, s in zip(target, source):
            _restore(t, s)


def _api_routes(routes):
    """Yield APIRoutes, descending into included routers (FastAPI >=0.14x wraps them in _IncludedRouter)."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        else:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                yield from _api_routes(inner.routes)


def install_exact_integer_bounds(app, modules):
    original = app.openapi
    cached = None

    def exact_schema():
        nonlocal cached
        schema = original()
        if schema is cached:
            return schema
        components = schema.get("components", {}).get("schemas", {})
        for module in modules:
            for model in vars(module).values():
                if isinstance(model, type) and issubclass(model, BaseModel) and model.__name__ in components:
                    _restore(components[model.__name__], model.model_json_schema())
        for route in _api_routes(app.routes):
            for method in route.methods:
                operation = schema.get("paths", {}).get(route.path_format, {}).get(method.lower(), {})
                parameters = {(p["in"], p["name"]): p for p in operation.get("parameters", [])}
                for kind, fields in (("path", route.dependant.path_params), ("query", route.dependant.query_params),
                                     ("header", route.dependant.header_params)):
                    for field in fields:
                        parameter = parameters.get((kind, field.alias))
                        if parameter is None:
                            continue
                        value_schema = parameter.get("schema", {})
                        targets = value_schema.get("anyOf", [value_schema])
                        for target in targets:
                            if target.get("type") != "integer":
                                continue
                            for metadata in field.field_info.metadata:
                                for bound, attr in BOUNDS:
                                    value = getattr(metadata, attr, None)
                                    if type(value) is int:
                                        target[bound] = value
                            _integer_format(target)
        cached = schema
        return schema

    app.openapi = exact_schema
