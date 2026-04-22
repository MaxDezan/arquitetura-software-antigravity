import re

from rapidfuzz import fuzz
from unidecode import unidecode


_FEATURE_PATTERNS = [
    r"\b(\d+)\s*(gb|tb|mb)\b",
    r"\b(\d+)\s*(mp|megapixel|mpx)\b",
    r'\b(\d+(?:[.,]\d+)?)\s*(polegadas|pol|")',
    r"\b(\d+)\s*(hz)\b",
    r"\b(20\d{2})\b",
]


def normalize(text: str) -> str:
    text = unidecode(text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def extract_features(text: str) -> set[str]:
    t = normalize(text)
    feats: set[str] = set()
    for pattern in _FEATURE_PATTERNS:
        for match in re.finditer(pattern, t):
            feats.add("".join(g.replace(",", ".") for g in match.groups() if g))
    return feats


def score_match(query: str, candidate: str) -> float:
    """0–100 similarity: fuzzy token overlap + numeric feature overlap."""
    nq, nc = normalize(query), normalize(candidate)
    if not nq or not nc:
        return 0.0

    token_ratio = fuzz.token_set_ratio(nq, nc)
    partial_ratio = fuzz.partial_ratio(nq, nc)
    base = 0.6 * token_ratio + 0.4 * partial_ratio

    q_feats = extract_features(query)
    c_feats = extract_features(candidate)
    if q_feats:
        overlap_frac = len(q_feats & c_feats) / len(q_feats)
        bonus = overlap_frac * 15
        penalty = 8 if (q_feats - c_feats) else 0
        base = base + bonus - penalty

    return max(0.0, min(100.0, base))


def rank_results(query: str, candidates: list, title_attr: str = "title") -> list:
    for c in candidates:
        title = getattr(c, title_attr, "") or ""
        c.match_score = round(score_match(query, title), 2)
    candidates.sort(key=lambda x: x.match_score, reverse=True)
    return candidates
