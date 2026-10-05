from fastapi import APIRouter, Query
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

router = APIRouter()


def _sanitize_label(value):
    if not value:
        return ""
    try:
        v = str(value)
    except Exception:
        return ""
    # remove digits and weird characters, keep letters and spaces
    import re

    v = re.sub(r"[^A-Za-zÀ-ÿ\s\-]", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    if any(c.isdigit() for c in v) or len(v) < 2:
        return ""
    return v.lower()


@router.get("/roi/calculer")
def calculer_roi(
    prix: float = Query(...),
    loyer_mensuel: float = Query(None),
    prix_nuit: float = Query(None),
    nuits_an: int = Query(90, ge=1, le=365),
):
    try:
        from models.roi_score.calculator import compute_roi
        return compute_roi(prix, loyer_mensuel=loyer_mensuel, prix_nuit=prix_nuit, nuits_an=nuits_an)
    except Exception as e:
        return {"statut": "erreur", "message": str(e)}


@router.get("/roi/top_zones")
def top_zones(limit: int = Query(10, ge=1, le=50)):
    try:
        from models.roi_score.calculator import top_zones as top
        raw = top(limit=limit)
        # final sanitize pass to avoid leaking malformed DB strings
        cleaned = []
        for z in raw:
            zl = z.get("zone_label") or _sanitize_label(z.get("ville")) or _sanitize_label(z.get("gouvernorat"))
            z["zone_label"] = zl or (z.get("ville") or z.get("gouvernorat") or "")
            # also sanitize gouvernorat/ville for safety
            z["gouvernorat"] = _sanitize_label(z.get("gouvernorat")) or ""
            z["ville"] = _sanitize_label(z.get("ville")) or ""
            cleaned.append(z)
        return {"data": cleaned}
    except Exception as e:
        return {"statut": "erreur", "message": str(e)}
