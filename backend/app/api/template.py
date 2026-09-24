from fastapi import APIRouter

from ..core.template import get_presets, validate_template
from ..models.template import TEMPLATE_PRESETS

router = APIRouter(prefix="/api", tags=["templates"])


@router.get("/presets")
async def list_presets():
    return {"success": True, "data": get_presets()}


@router.post("/validate")
async def validate(req: dict):
    template = req.get("template", "")
    ok, errors = validate_template(template)
    return {"valid": ok, "errors": errors}
