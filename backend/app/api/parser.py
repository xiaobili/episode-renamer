from fastapi import APIRouter

from ..models.api import ParseRequest, BatchParseRequest
from ..core.parser import parse_filename, batch_parse_filenames

router = APIRouter(prefix="/api", tags=["parser"])


@router.post("/parse")
async def parse_single(req: ParseRequest):
    result = parse_filename(req.filename, req.parent_dir)
    return {"success": True, "data": result.model_dump()}


@router.post("/parse/batch")
async def parse_batch(req: BatchParseRequest):
    results = batch_parse_filenames(req.filenames, req.parent_dirs)
    return {
        "success": True,
        "data": [r.model_dump() for r in results],
        "total": len(results),
    }
