"""Vocabulary for "games like X": genre weights, keyword groups and conflicts.

Data only — no logic. Every module in this package reads its signal names from
here so a term is never spelled out in two places.
"""

PLATFORM_GENRES = {"pc", "steam", "mac", "linux", "playstation", "xbox", "nintendo", "mobile"}
LOW_SIGNAL_GENRES = {"adventure", "action", "indie", "casual", "simulation", "sports"}
IGNORED_GENRES = {"uncategorized", "deal"}

DEFAULT_GENRE_WEIGHT = 13
LOW_SIGNAL_GENRE_WEIGHT = 7
DEFAULT_SIGNAL_WEIGHT = 18
STRONG_MATCH_WEIGHT = 16

GENRE_WEIGHTS: dict[str, float] = {
    "rpg": 16, "strategy": 18, "jrpg": 22, "soulslike": 24, "stealth": 19, "horror": 20,
    "puzzle": 18, "racing": 20, "platformer": 20, "shooter": 18, "fighting": 20,
    "survival": 22, "narrative": 20, "isometric": 28, "tactical": 30, "turn-based": 30,
    "turn based": 30, "crpg": 34, "co-op": 12, "coop": 12,
    "actionAdventure": 16, "cinematic": 22, "thirdPerson": 24, "postApocalyptic": 28,
    "openWorld": 12, "firstPerson": 10, "immersiveSim": 22,
    "dialogueRpg": 34, "detective": 30, "political": 18, "nonCombat": 24,
}

KEYWORD_GROUPS: dict[str, list[str]] = {
    "crpg": ["crpg", "computer role-playing", "tabletop", "dungeons", "d&d", "pathfinder",
             "forgotten realms", "baldur s gate", "baldur's gate", "planescape",
             "pillars of eternity", "divinity original sin", "wasteland"],
    "tactical": ["tactical", "turn-based", "turn based", "positioning", "party-based", "party based"],
    "isometric": ["isometric"],
    "party": ["party", "companions", "companion", "origin story"],
    "narrative": ["narrative", "dialogue", "choices", "choice", "reactive world", "story-rich",
                  "story rich", "story-driven", "story driven", "storytelling"],
    "dialogueRpg": ["dialogue-rich", "dialogue rich", "internal voices", "dice rolls", "skill checks",
                    "role-playing", "role playing", "conversations"],
    "detective": ["detective", "murder", "investigation", "case", "mystery"],
    "political": ["political", "ideology", "ideologies", "revolution", "communist", "fascist"],
    "nonCombat": ["instead of combat", "without combat", "no combat"],
    "cinematic": ["cinematic", "set piece", "set-piece", "character-driven", "character driven",
                  "emotional", "single-player narrative", "single player narrative"],
    "fantasy": ["fantasy", "realm", "demons", "souls", "mythic", "magic", "dragon"],
    "openWorld": ["open world", "sandbox"],
    "postApocalyptic": ["post-apocalyptic", "post apocalyptic", "apocalypse", "pandemic", "infected",
                        "zombie", "zombies", "ravaged world"],
    "thirdPerson": ["third-person", "third person", "over-the-shoulder", "over the shoulder"],
    "firstPerson": ["first-person", "first person", "fps", "vr"],
    "actionAdventure": ["action-adventure", "action adventure"],
    "immersiveSim": ["immersive sim", "systemic", "player choice", "emergent gameplay"],
    "actionCombat": ["soulslike", "hack and slash", "fast-paced", "action combat", "shooter"],
    "shooter": ["shooter", "fps", "first person shooter", "third person shooter", "gunplay"],
    "stealth": ["stealth", "sneak", "assassin"],
    "horror": ["horror", "survival horror", "psychological horror"],
    "survival": ["survival", "crafting", "base building"],
    "puzzle": ["puzzle", "logic", "physics-based", "physics based"],
    "platformer": ["platformer", "metroidvania", "side-scroller", "side scroller"],
    "racing": ["racing", "driving", "motorsport"],
    "management": ["management", "city builder", "colony sim", "automation"],
    "jrpg": ["jrpg", "japanese", "anime"],
    "roguelike": ["roguelike", "rogue-like", "roguelite"],
}

CONFLICTING_GROUPS: list[tuple[str, str]] = [
    ("crpg", "jrpg"), ("crpg", "soulslike"), ("crpg", "roguelike"),
    ("tactical", "soulslike"), ("tactical", "roguelike"), ("narrative", "shooter"),
    ("thirdPerson", "firstPerson"),
]

SPECIALIZED_SIGNAL_GROUPS = [
    "crpg", "tactical", "isometric", "jrpg", "soulslike", "roguelike", "shooter",
    "stealth", "horror", "survival", "puzzle", "platformer", "racing", "management",
    "narrative", "cinematic", "thirdPerson", "postApocalyptic", "actionAdventure",
    "openWorld", "immersiveSim", "dialogueRpg", "detective", "political", "nonCombat",
]

CRPG_TRIGGER_SIGNALS = {"crpg", "tactical", "isometric"}
CRPG_COMPATIBLE_SIGNALS = {"crpg", "tactical", "isometric", "party", "narrative"}
CRPG_STRUCTURE_SIGNALS = {"tactical", "isometric", "turn-based", "turn based", "party"}
DEEP_RPG_STRUCTURE_SIGNALS = {
    "crpg", "party", "isometric", "tactical", "turn-based", "turn based",
    "dialogueRpg", "detective", "nonCombat",
}
DEEP_RPG_CORE_SIGNALS = {"crpg", "party", "isometric", "tactical", "dialogueRpg", "detective"}
DEEP_RPG_DEPTH_SIGNALS = DEEP_RPG_CORE_SIGNALS | {"narrative"}
CINEMATIC_ACTION_SIGNALS = {"cinematic", "thirdPerson", "postApocalyptic", "survival", "horror"}
CINEMATIC_FOCUS_SIGNALS = {"cinematic", "thirdPerson", "narrative"}
HORROR_ADJACENT_SIGNALS = {"narrative", "cinematic", "stealth", "postApocalyptic", "actionAdventure"}
SHOOTER_SOFTENING_SIGNALS = {"horror", "survival", "narrative", "cinematic", "thirdPerson", "stealth"}
SHOOTER_TOLERANT_SIGNALS = {
    "horror", "survival", "stealth", "narrative", "cinematic", "postApocalyptic",
}

KNOWN_SERIES_SIGNALS: dict[str, set[str]] = {
    "last us": {"thirdPerson", "cinematic", "narrative", "stealth", "survival", "horror", "postApocalyptic"},
    "uncharted": {"thirdPerson", "cinematic", "narrative", "actionAdventure"},
    "tomb raider": {"thirdPerson", "cinematic", "survival", "actionAdventure"},
    "resident evil": {"thirdPerson", "horror", "survival", "shooter"},
    "dead space": {"thirdPerson", "horror", "survival", "shooter"},
    "alan wake": {"thirdPerson", "cinematic", "narrative", "horror"},
}

SIGNAL_SEARCH_TERMS: dict[str, list[str]] = {
    "thirdPerson": ["third person", "third-person", "over the shoulder", "over-the-shoulder"],
    "cinematic": ["cinematic", "story-driven", "single-player narrative", "single player narrative"],
    "postApocalyptic": ["post-apocalyptic", "post apocalyptic", "pandemic", "infected", "zombie"],
    "stealth": ["stealth"],
    "survival": ["survival horror", "survival"],
}
SIGNAL_SEARCH_PRIORITY = ["thirdPerson", "cinematic", "postApocalyptic", "stealth", "survival"]
SIGNAL_SEARCH_TRIGGERS = {
    "thirdPerson", "cinematic", "postApocalyptic", "survival", "horror", "stealth",
}
