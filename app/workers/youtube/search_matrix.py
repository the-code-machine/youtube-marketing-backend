"""
app/workers/youtube/search_matrix.py

GLOBAL TARGETING | 24 Keys | 10 Categories
═══════════════════════════════════════════════════════════════════

BUSINESS GOAL:
  Target YouTube creators who actively upload and NEED:
    → More views / watch time
    → Subscriber growth
    → YouTube Ads management
    → YouTube SEO optimization
    → Channel growth services

  Best signal = creator just uploaded a NEW video
  They care about performance RIGHT NOW = perfect outreach timing

GLOBAL REGIONS:
  US = United States     (largest YouTube market, highest CPM)
  GB = United Kingdom    (English, high CPM, active creator scene)
  IN = India             (massive volume, fast-growing creator economy)
  CA = Canada            (English, high CPM, diaspora creators)
  AU = Australia         (English, growing creator scene)
  PH = Philippines       (massive English YouTube creator market)
  NG = Nigeria           (fastest growing YouTube creator market globally)
  AE = UAE               (high CPM, NRI creators, business/finance)

QUOTA MATH — 24 Keys:
  24 keys × 10,000     = 240,000 units/day
  3 runs/day budget    =  80,000 units/run
  Reserve for fetch    =   2,000 units/run
  Available for search =  78,000 units/run

  10 categories × 40 jobs × 200 units = 80,000 units/run ✅
  Per category: 10 queries × 4 regions × 1 language = 40 jobs

DAILY OUTPUT ESTIMATE:
  Per run:    ~10,000–15,000 unique videos
  3 runs/day: ~18,000–25,000 unique NEW videos/day
  Channels:   ~8,000–12,000 unique channels/day
  Email rate: ~15–20% globally
  Leads/day:  ~1,000–2,000 ✅
"""

from typing import TypedDict


class SearchJob(TypedDict):
    query: str
    region_code: str
    language: str
    category_name: str


SEARCH_MATRIX: dict[str, dict] = {

    # ═══════════════════════════════════════════════════════════════════
    # 1. MUSIC CREATORS
    # WHY: Every new song release = creator desperately needs views NOW
    #      Music labels + indie artists = biggest buyers of YouTube promo
    # Volume: 10,000–20,000 new music videos/day globally ✅✅
    # Lead value: VERY HIGH — views & ads are core need
    # ═══════════════════════════════════════════════════════════════════
    "Music Creators": {
        "queries": [
            "official music video 2026",
            "new song 2026",
            "new single official video",
            "indie artist music video",
            "hip hop music video 2026",
            "rnb music video 2026",
            "afrobeats music video 2026",
            "latin music video 2026",
            "pop song official video 2026",
            "underground music video 2026",
        ],
        "regions": ["US", "GB", "NG", "PH"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },

    # ═══════════════════════════════════════════════════════════════════
    # 2. PODCAST CREATORS
    # WHY: Podcasters launching on YouTube need subscriber growth urgently
    #      Professional/business audience = understands marketing ROI
    # Volume: 2,000–5,000 new episodes/day on YouTube globally
    # Lead value: HIGH — they have budget, understand services
    # ═══════════════════════════════════════════════════════════════════
    "Podcast Creators": {
        "queries": [
            "podcast episode 2026",
            "business podcast new episode",
            "entrepreneur interview podcast",
            "true crime podcast episode",
            "self improvement podcast new",
            "health wellness podcast episode",
            "technology podcast new episode",
            "comedy podcast new episode",
            "sports podcast episode new",
            "news commentary podcast new",
        ],
        "regions": ["US", "GB", "CA", "AU"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },

    # ═══════════════════════════════════════════════════════════════════
    # 3. FINANCE & INVESTING
    # WHY: Highest CPM niche — creators understand ROI, will pay for growth
    #      Extremely competitive → SEO + subscribers = survival for them
    # Volume: 3,000–6,000 new finance videos/day globally
    # Lead value: VERY HIGH — high CPM = they profit from every view
    # ═══════════════════════════════════════════════════════════════════
    "Finance & Investing": {
        "queries": [
            "stock market investing 2026",
            "investing for beginners guide",
            "personal finance tips new",
            "crypto trading tutorial 2026",
            "passive income strategy new",
            "financial freedom how to",
            "dividend investing guide",
            "real estate investing beginner",
            "trading tutorial beginners",
            "how to budget money save",
        ],
        "regions": ["US", "GB", "CA", "AU"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },

    # ═══════════════════════════════════════════════════════════════════
    # 4. EDUCATION & TECH
    # WHY: Tutorial channels grow via search = YouTube SEO is critical
    #      Tech = high CPM + global audience + creators understand digital
    # Volume: 5,000–10,000 new tutorial videos/day globally
    # Lead value: HIGH — tech savvy = easy to sell digital services
    # ═══════════════════════════════════════════════════════════════════
    "Education & Tech": {
        "queries": [
            "coding tutorial beginner 2026",
            "programming tutorial beginners",
            "web development tutorial new",
            "python tutorial beginners",
            "data science tutorial new",
            "machine learning tutorial 2026",
            "javascript tutorial beginners",
            "tech career advice guide",
            "software engineering tutorial",
            "ai tools tutorial how to",
        ],
        "regions": ["US", "GB", "IN", "PH"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },

    # ═══════════════════════════════════════════════════════════════════
    # 5. GAMING CREATORS
    # WHY: #1 YouTube category by volume — most competitive niche
    #      Every gamer wants more subs/views to monetize faster
    #      Young creators learning marketing = open to services
    # Volume: 50,000–100,000 new videos/day globally ✅✅✅
    # Lead value: MEDIUM-HIGH — huge volume compensates lower conversion
    # ═══════════════════════════════════════════════════════════════════
    "Gaming Creators": {
        "queries": [
            "gaming channel new video 2026",
            "lets play gameplay 2026",
            "game review new release 2026",
            "fps gameplay montage new",
            "minecraft gameplay 2026",
            "roblox new video 2026",
            "mobile gaming gameplay new",
            "esports highlights new video",
            "open world gameplay walkthrough",
            "gaming tips strategy guide new",
        ],
        "regions": ["US", "GB", "IN", "PH"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },

    # ═══════════════════════════════════════════════════════════════════
    # 6. FITNESS & HEALTH
    # WHY: Fitness creators are extremely brand-conscious about growth
    #      Views = sponsorship deal value = they invest in marketing
    #      January + June peak seasons = high urgency periods
    # Volume: 5,000–10,000 new videos/day globally
    # Lead value: HIGH — brand deal motivation = pay for views
    # ═══════════════════════════════════════════════════════════════════
    "Fitness & Health": {
        "queries": [
            "workout tutorial beginner 2026",
            "home workout no equipment new",
            "weight loss workout beginner",
            "gym workout routine new",
            "yoga for beginners new video",
            "hiit workout tutorial new",
            "bodybuilding diet tips new",
            "calisthenics beginner tutorial",
            "mental health tips new video",
            "healthy lifestyle routine vlog",
        ],
        "regions": ["US", "GB", "AU", "CA"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },

    # ═══════════════════════════════════════════════════════════════════
    # 7. FOOD & COOKING
    # WHY: #2 largest YouTube niche — massive daily upload volume
    #      Food creators need views to hit monetization threshold fast
    #      Brand deals in food niche are extremely lucrative
    # Volume: 8,000–15,000 new videos/day globally
    # Lead value: HIGH — monetization threshold = urgent need
    # ═══════════════════════════════════════════════════════════════════
    "Food & Cooking": {
        "queries": [
            "cooking tutorial easy recipe new",
            "recipe video beginner cooking",
            "food vlog what i eat new",
            "street food tour new video",
            "restaurant review vlog new",
            "meal prep beginner guide new",
            "baking tutorial beginner new",
            "healthy recipes easy cooking",
            "international cuisine recipe new",
            "budget cooking easy recipes",
        ],
        "regions": ["US", "GB", "IN", "AU"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },

    # ═══════════════════════════════════════════════════════════════════
    # 8. COMEDY & ENTERTAINMENT
    # WHY: Comedy channels are 100% algorithm dependent for views
    #      They KNOW their content lives or dies by YouTube promotion
    #      Most monetized via AdSense = directly understand view value
    # Volume: 10,000–20,000 new videos/day globally
    # Lead value: HIGH — algorithm anxiety = receptive to services
    # ═══════════════════════════════════════════════════════════════════
    "Comedy & Entertainment": {
        "queries": [
            "comedy skit funny video 2026",
            "stand up comedy new video",
            "funny prank video new 2026",
            "sketch comedy new video",
            "reaction video new 2026",
            "roast video comedy new",
            "entertainment vlog new video",
            "comedy series episode new",
            "web series new episode 2026",
            "satirical comedy new video",
        ],
        "regions": ["US", "GB", "NG", "IN"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },

    # ═══════════════════════════════════════════════════════════════════
    # 9. BUSINESS & ENTREPRENEURSHIP
    # WHY: Best possible lead — business owners WITH marketing budget
    #      They already spend on ads/marketing in their own business
    #      Understand ROI completely = easiest sale
    # Volume: 3,000–6,000 new videos/day globally
    # Lead value: VERY HIGH — budget + understanding = best conversion ✅
    # ═══════════════════════════════════════════════════════════════════
    "Business & Entrepreneurship": {
        "queries": [
            "how to start a business 2026",
            "entrepreneur vlog new video",
            "online business tutorial new",
            "side hustle ideas new video",
            "passive income strategy new",
            "ecommerce business tutorial",
            "dropshipping tutorial beginner",
            "freelancing tips career new",
            "agency owner business vlog",
            "small business owner tips",
        ],
        "regions": ["US", "GB", "CA", "AU"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },

    # ═══════════════════════════════════════════════════════════════════
    # 10. LIFESTYLE & TRAVEL VLOGS
    # WHY: Vloggers want subscribers for brand sponsorship deals
    #      Subscriber count = their entire business metric
    #      Daily uploaders = constant fresh new leads every run
    # Volume: 10,000–20,000 new vlogs/day globally
    # Lead value: MEDIUM-HIGH — subscriber focused = buy growth services
    # ═══════════════════════════════════════════════════════════════════
    "Lifestyle & Travel Vlogs": {
        "queries": [
            "travel vlog new video 2026",
            "day in my life vlog new",
            "moving abroad living vlog new",
            "digital nomad vlog 2026",
            "city tour vlog new video",
            "lifestyle vlog daily routine",
            "budget travel vlog new",
            "solo travel vlog new video",
            "expat life vlog new 2026",
            "vanlife road trip vlog new",
        ],
        "regions": ["US", "GB", "AU", "CA"],
        "languages": ["en"],
        # 10 × 4 × 1 = 40 jobs × 200 = 8,000 units/run
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_search_jobs(category_name: str) -> list[SearchJob]:
    """
    Expands the matrix for ONE category into a flat list of search jobs.
    Includes case-insensitive fallback matching.
    """
    config = SEARCH_MATRIX.get(category_name)

    if not config:
        # Case-insensitive fallback
        for key in SEARCH_MATRIX:
            if key.lower() == category_name.lower():
                config = SEARCH_MATRIX[key]
                break

    if not config:
        print(
            f"⚠️  No matrix entry for '{category_name}'. "
            f"Available: {list(SEARCH_MATRIX.keys())}"
        )
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

    units = len(jobs) * 200
    print(
        f"📋 [{category_name}] "
        f"{len(config['queries'])}q × {len(config['regions'])}r × "
        f"{len(config['languages'])}l = {len(jobs)} jobs | {units:,} units/run"
    )
    return jobs


def get_all_jobs() -> dict[str, list[SearchJob]]:
    """Returns jobs for ALL categories."""
    return {cat: get_search_jobs(cat) for cat in SEARCH_MATRIX}


def print_quota_summary():
    """
    Prints full quota and run feasibility summary.
    Run: python app/workers/youtube/search_matrix.py
    """
    print("\n" + "═" * 68)
    print("📊 QUOTA SUMMARY — target_count=100 (200 units/job)")
    print("═" * 68)

    total_jobs = 0
    total_units = 0

    for cat_name, config in SEARCH_MATRIX.items():
        jobs = (
            len(config["queries"])
            * len(config["regions"])
            * len(config["languages"])
        )
        units = jobs * 200
        total_jobs += jobs
        total_units += units
        print(f"  {cat_name:<38} {jobs:>3} jobs  {units:>8,} units")

    print("─" * 68)
    print(f"  {'TOTAL':<38} {total_jobs:>3} jobs  {total_units:>8,} units")
    print()
    for keys in [8, 12, 16, 20, 24]:
        budget = keys * 10_000
        runs = budget // total_units
        print(
            f"  {keys:>2} keys ({budget:>7,} units) → "
            f"{runs} full run{'s' if runs != 1 else ''}/day  "
            f"{'✅' if runs >= 3 else '⚠️ ' if runs >= 1 else '❌'}"
        )
    print("═" * 68 + "\n")


if __name__ == "__main__":
    print_quota_summary()