import re
from typing import Optional

from unidecode import unidecode

from comparador.domain.models import AUTO_LINK_THRESHOLD, MANUAL_REVIEW_THRESHOLD


def canonical_product_name(name: str) -> str:
    """Stable form used to dedup products across runs (case/accents-insensitive)."""
    s = unidecode(name or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def link_status_for_score(match_score: float) -> Optional[str]:
    """Returns 'auto', 'pending', or None (score too low to persist)."""
    if match_score >= AUTO_LINK_THRESHOLD:
        return "auto"
    if match_score >= MANUAL_REVIEW_THRESHOLD:
        return "pending"
    return None
