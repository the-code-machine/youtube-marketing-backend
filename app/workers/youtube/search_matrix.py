"""
app/workers/youtube/search_matrix.py

Defines the full search matrix for each category:
  - Multiple query variations (to avoid hitting the same ~500 result cap)
  - Multiple region codes  (IN + diaspora markets)
  - Multiple language codes (hi + en)

Each unique (query × region × language) combination = one search job.
A single search job can return up to 500 videos (10 pages × 50 results).

MATH per category:
  Indian Music      → 14 queries × 4 regions × 2 langs = 112 jobs → up to 56,000 raw results
  Indian Podcasts   → 12 queries × 3 regions × 2 langs =  72 jobs → up to 36,000 raw results
  Finance           → 13 queries × 4 regions × 2 langs = 104 jobs → up to 52,000 raw results
  Education & Tech  → 14 queries × 4 regions × 2 langs = 112 jobs → up to 56,000 raw results

After deduplication you realistically get 5,000–15,000 unique NEW videos/day across all categories.
"""

from typing import TypedDict


class SearchJob(TypedDict):
    query: str
    region_code: str
    language: str
    category_name: str


# ──────────────────────────────────────────────────────────────────────────────
# MASTER SEARCH MATRIX
# Keys match TargetCategory.name exactly (case-sensitive)
# ──────────────────────────────────────────────────────────────────────────────

SEARCH_MATRIX: dict[str, dict] = {

    # ═══════════════════════════════════════════════════════════════
    # 1. INDIAN MUSIC  (id=1)
    # ═══════════════════════════════════════════════════════════════
    "Indian Music": {
        "queries": [
            # Core discovery queries
            "official music video 2026",
            "new song 2026",
            "punjabi song 2026",
            "hindi song 2026",
            # Genre-specific
            "bollywood song new",
            "haryanvi song 2026",
            "bhojpuri song 2026",
            "rajasthani song 2026",
            "devotional song hindi 2026",
            "independent artist india music",
            # High-volume long-tail
            "new album release india",
            "music video india upcoming",
            "desi hip hop 2026",
            "lo-fi hindi music",
        ],
        "regions": ["IN", "GB", "CA", "AE"],   # India + UK/Canada diaspora + Gulf
        "languages": ["hi", "en"],
    },

    # ═══════════════════════════════════════════════════════════════
    # 2. INDIAN PODCASTS  (id=2)
    # ═══════════════════════════════════════════════════════════════
    "Indian Podcasts": {
        "queries": [
            # Core
            "business podcast hindi 2026",
            "startup india podcast",
            "entrepreneur interview hindi",
            "hindi podcast episode",
            # Niche angles (find channels missed by broad query)
            "founder story india",
            "motivational podcast india hindi",
            "investor talk india",
            "saas startup india podcast",
            "side hustle india hindi",
            "career advice india hindi",
            "self improvement hindi podcast",
            "real estate india hindi",
        ],
        "regions": ["IN", "GB", "CA"],
        "languages": ["hi", "en"],
    },

    # ═══════════════════════════════════════════════════════════════
    # 3. FINANCE & STOCK MARKET  (id=3)
    # ═══════════════════════════════════════════════════════════════
    "Finance & Stock Market": {
        "queries": [
            # Core (from DB query description)
            "stock market hindi 2026",
            "trading tutorial india",
            "investment guide hindi",
            "crypto india 2026",
            # Expanded long-tail
            "mutual fund india hindi",
            "nifty sensex analysis hindi",
            "options trading india hindi",
            "personal finance hindi",
            "financial freedom india hindi",
            "demat account india tutorial",
            "share market basics hindi",
            "swing trading india",
            "fundamental analysis hindi",
        ],
        "regions": ["IN", "GB", "AE", "SG"],  # Gulf + Singapore NRI investors
        "languages": ["hi", "en"],
    },

    # ═══════════════════════════════════════════════════════════════
    # 4. EDUCATION & TECH CREATORS  (id=4)
    # ═══════════════════════════════════════════════════════════════
    "Education & Tech Creators": {
        "queries": [
            # Core (from DB query description)
            "coding tutorial hindi",
            "software engineering india",
            "tech career hindi",
            "python tutorial hindi",
            # Expanded
            "web development hindi 2026",
            "data science hindi tutorial",
            "machine learning hindi",
            "javascript tutorial hindi",
            "react tutorial india",
            "django tutorial hindi",
            "placement preparation india",
            "dsa coding interview india",
            "ai tools india hindi",
            "cloud computing india hindi",
        ],
        "regions": ["IN", "GB", "CA", "US"],
        "languages": ["hi", "en"],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: Expand matrix into flat list of SearchJob dicts
# ──────────────────────────────────────────────────────────────────────────────

def get_search_jobs(category_name: str) -> list[SearchJob]:
    """
    Expands the matrix for ONE category into a flat list of search jobs.

    Each job is a unique (query × region × language) combination.
    The main_worker iterates through these, calling search_videos() per job.

    Returns [] if category_name is not found (safe fallback).
    """
    config = SEARCH_MATRIX.get(category_name)

    if not config:
        print(f"⚠️  No search matrix entry for category '{category_name}'. Skipping.")
        return []

    jobs: list[SearchJob] = []

    for query in config["queries"]:
        for region in config["regions"]:
            for language in config["languages"]:
                jobs.append(
                    SearchJob(
                        query=query,
                        region_code=region,
                        language=language,
                        category_name=category_name,
                    )
                )

    total = len(jobs)
    max_results = total * 500  # theoretical max (10 pages × 50 per job)
    print(
        f"📋 [{category_name}] Search matrix expanded: "
        f"{len(config['queries'])} queries × {len(config['regions'])} regions × "
        f"{len(config['languages'])} languages = {total} jobs "
        f"(up to {max_results:,} raw results)"
    )

    return jobs


def get_all_jobs() -> dict[str, list[SearchJob]]:
    """Returns search jobs for ALL categories. Useful for diagnostics."""
    return {cat: get_search_jobs(cat) for cat in SEARCH_MATRIX}