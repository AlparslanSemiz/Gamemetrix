"""
Centralized rating source registry.

Source taxonomy:
  Primary rating   — Metacritic, OpenCritic, IGDB, Steam
  Supplementary    — RAWG (display/enrichment only; never fills a primary slot)
  Popularity       — SteamSpy (ownership / player activity; never a rating)
  Price            — CheapShark, ITAD (deals / value; never a rating)
  Metadata         — FreeToGame (catalog / availability; never a rating)

Only primary sources contribute to GameMetrix Score.
Weight 0.0 guarantees a source never enters the score calculation.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDef:
    key: str
    display_name: str
    # "critic" | "user" | "aggregate" | "popularity" | "price" | "metadata"
    source_type: str
    # Weight in the Bayesian composite — 0.0 for non-rating sources
    weight: float
    is_primary: bool
    # True = only applicable when a game has a PC/Steam platform entry
    requires_pc: bool
    # Prior vote count used in Bayesian shrinkage (mirrors PRIOR_VOTE_COUNTS in sync.py)
    prior_count: int
    # Lower number = shown first in UI source breakdown
    display_priority: int


REGISTRY: dict[str, SourceDef] = {
    "Metacritic": SourceDef(
        key="Metacritic",
        display_name="Metacritic",
        source_type="critic",
        weight=0.32,
        is_primary=True,
        requires_pc=False,
        prior_count=10,
        display_priority=1,
    ),
    "OpenCritic": SourceDef(
        key="OpenCritic",
        display_name="OpenCritic",
        source_type="critic",
        weight=0.28,
        is_primary=True,
        requires_pc=False,
        prior_count=10,
        display_priority=2,
    ),
    "IGDB": SourceDef(
        key="IGDB",
        display_name="IGDB",
        source_type="user",
        weight=0.15,
        is_primary=True,
        requires_pc=False,
        prior_count=15,
        display_priority=3,
    ),
    "Steam": SourceDef(
        key="Steam",
        display_name="Steam",
        source_type="user",
        weight=0.25,
        is_primary=True,
        requires_pc=True,
        prior_count=800,
        display_priority=4,
    ),
    "RAWG": SourceDef(
        key="RAWG",
        display_name="RAWG",
        source_type="aggregate",
        weight=0.0,
        is_primary=False,
        requires_pc=False,
        prior_count=150,
        display_priority=5,
    ),
    # ── Non-rating support sources — weight 0.0, never enter GameMetrix Score ─
    "SteamSpy": SourceDef(
        key="SteamSpy",
        display_name="SteamSpy",
        source_type="popularity",
        weight=0.0,
        is_primary=False,
        requires_pc=True,
        prior_count=0,
        display_priority=99,
    ),
    "CheapShark": SourceDef(
        key="CheapShark",
        display_name="CheapShark",
        source_type="price",
        weight=0.0,
        is_primary=False,
        requires_pc=True,
        prior_count=0,
        display_priority=99,
    ),
    "FreeToGame": SourceDef(
        key="FreeToGame",
        display_name="FreeToGame",
        source_type="metadata",
        weight=0.0,
        is_primary=False,
        requires_pc=False,
        prior_count=0,
        display_priority=99,
    ),
    "ITAD": SourceDef(
        key="ITAD",
        display_name="IsThereAnyDeal",
        source_type="price",
        weight=0.0,
        is_primary=False,
        requires_pc=True,
        prior_count=0,
        display_priority=99,
    ),
}

# Sources that contribute to score and confidence calculations.
RATING_SOURCES: frozenset[str] = frozenset({"Metacritic", "OpenCritic", "IGDB", "Steam"})

# Convenience sets (immutable)
PRIMARY_SOURCES: frozenset[str] = frozenset(
    k for k, v in REGISTRY.items() if v.is_primary
)
CRITIC_SOURCES: frozenset[str] = frozenset(
    k for k, v in REGISTRY.items() if v.source_type == "critic"
)
USER_RATING_SOURCES: frozenset[str] = frozenset(
    k for k, v in REGISTRY.items() if v.source_type == "user" and v.is_primary
)
POPULARITY_SOURCES: frozenset[str] = frozenset(
    k for k, v in REGISTRY.items() if v.source_type == "popularity"
)
PRICE_SOURCES: frozenset[str] = frozenset(
    k for k, v in REGISTRY.items() if v.source_type == "price"
)

PC_PLATFORM_KEYS: frozenset[str] = frozenset({
    "pc", "windows", "microsoft windows", "pc windows", "steam",
})


def applicable_for_game(platforms: list[str]) -> frozenset[str]:
    """
    Return the set of *rating* source keys applicable to a game.

    A game with no PC platform entry should not be penalised for missing
    Steam data — Steam is simply not applicable.
    """
    is_pc = any(p.lower() in PC_PLATFORM_KEYS for p in platforms)
    return frozenset(
        k for k, v in REGISTRY.items()
        if v.is_primary and (not v.requires_pc or is_pc)
    )
