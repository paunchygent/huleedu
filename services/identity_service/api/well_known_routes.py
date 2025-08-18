from __future__ import annotations

from dishka import FromDishka
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from services.identity_service.implementations.jwks_store import JwksStore

bp = Blueprint("well_known", __name__, url_prefix="/.well-known")


@bp.get("/jwks.json")
@inject
async def jwks(jwks_store: FromDishka[JwksStore]) -> tuple[Response, int]:
    response = jwks_store.get_jwks()
    return jsonify(response.model_dump(mode="json")), 200
