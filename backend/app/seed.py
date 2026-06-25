from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Game


SEED_GAMES = [
    {
        "title": "Baldur's Gate 3",
        "slug": "baldurs-gate-3",
        "summary": "A party-based role-playing epic set in the Forgotten Realms, where every dialogue choice, combat decision, and companion relationship can reshape the campaign. It combines turn-based tactical encounters with unusually reactive quest design, making player agency feel visible from small village disputes to world-ending threats.",
        "cover_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/co670h.jpg",
        "release_date": date(2023, 8, 3),
        "release_year": 2023,
        "metrix_score": 96.4,
        "critic_score": 96.0,
        "user_score": 94.0,
        "genres": ["RPG", "Strategy", "Adventure"],
        "platforms": ["PC", "PlayStation 5", "Xbox Series X/S"],
        "developer": "Larian Studios",
        "publisher": "Larian Studios",
        "playtime_minutes": 4500,
        "source_scores": [
            {"source": "Metacritic", "score": 96, "scale": 100, "status": "live", "review_count": 113},
            {"source": "OpenCritic", "score": 96, "scale": 100, "status": "live", "review_count": 208},
            {"source": "Steam", "score": 95, "scale": 100, "status": "live", "review_count": 620000},
        ],
    },
    {
        "title": "Elden Ring",
        "slug": "elden-ring",
        "summary": "A vast action RPG built around mystery, danger, and discovery across the Lands Between. Its open world rewards curiosity with hidden legacy dungeons, strange characters, and demanding boss fights, while the flexible build system lets players approach its brutal combat through magic, stealth, summons, heavy weapons, or pure reflex.",
        "cover_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/co4jni.jpg",
        "release_date": date(2022, 2, 25),
        "release_year": 2022,
        "metrix_score": 95.7,
        "critic_score": 96.0,
        "user_score": 91.0,
        "genres": ["Action", "RPG", "Adventure"],
        "platforms": ["PC", "PlayStation 5", "Xbox Series X/S"],
        "developer": "FromSoftware",
        "publisher": "Bandai Namco",
        "playtime_minutes": 3600,
        "source_scores": [
            {"source": "Metacritic", "score": 96, "scale": 100, "status": "live", "review_count": 95},
            {"source": "OpenCritic", "score": 95, "scale": 100, "status": "live", "review_count": 177},
            {"source": "Steam", "score": 92, "scale": 100, "status": "live", "review_count": 780000},
        ],
    },
    {
        "title": "Hades",
        "slug": "hades",
        "summary": "A fast roguelike action game about escaping the underworld again and again, with each failed run feeding character relationships, weapon mastery, and story progression. Its combat is immediate and expressive, but the lasting hook is how every return to the House of Hades reveals new dialogue, rivalries, and emotional texture.",
        "cover_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/co39vc.jpg",
        "release_date": date(2020, 9, 17),
        "release_year": 2020,
        "metrix_score": 93.8,
        "critic_score": 93.0,
        "user_score": 97.0,
        "genres": ["Action", "Roguelike", "Indie"],
        "platforms": ["PC", "Nintendo Switch", "PlayStation 5", "Xbox Series X/S"],
        "developer": "Supergiant Games",
        "publisher": "Supergiant Games",
        "playtime_minutes": 1500,
        "source_scores": [
            {"source": "Metacritic", "score": 93, "scale": 100, "status": "live", "review_count": 78},
            {"source": "OpenCritic", "score": 94, "scale": 100, "status": "live", "review_count": 107},
            {"source": "Steam", "score": 98, "scale": 100, "status": "live", "review_count": 290000},
        ],
    },
    {
        "title": "Alan Wake 2",
        "slug": "alan-wake-2",
        "summary": "A survival horror sequel that splits its story between an FBI investigation and a nightmare writer's room. It mixes tense resource management, crime-scene deduction, live-action fragments, and surreal shifting spaces to create a thriller where narrative structure itself becomes part of the threat.",
        "cover_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/co6g32.jpg",
        "release_date": date(2023, 10, 27),
        "release_year": 2023,
        "metrix_score": 89.6,
        "critic_score": 89.0,
        "user_score": 86.0,
        "genres": ["Horror", "Adventure", "Action"],
        "platforms": ["PC", "PlayStation 5", "Xbox Series X/S"],
        "developer": "Remedy Entertainment",
        "publisher": "Epic Games Publishing",
        "playtime_minutes": 1080,
        "source_scores": [
            {"source": "Metacritic", "score": 89, "scale": 100, "status": "live", "review_count": 72},
            {"source": "OpenCritic", "score": 90, "scale": 100, "status": "live", "review_count": 130},
            {"source": "IGDB", "score": 88, "scale": 100, "status": "live", "review_count": 45},
        ],
    },
    {
        "title": "Disco Elysium: The Final Cut",
        "slug": "disco-elysium-the-final-cut",
        "summary": "A dialogue-rich detective RPG about a broken investigator trying to solve a murder while rebuilding, or further ruining, his own identity. Instead of traditional combat, it uses internal voices, political instincts, dice rolls, and deeply written conversations to turn thought, shame, ideology, and empathy into mechanics.",
        "cover_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/co2n12.jpg",
        "release_date": date(2021, 3, 30),
        "release_year": 2021,
        "metrix_score": 92.9,
        "critic_score": 92.0,
        "user_score": 91.0,
        "genres": ["RPG", "Adventure", "Narrative"],
        "platforms": ["PC", "Nintendo Switch", "PlayStation 5", "Xbox Series X/S"],
        "developer": "ZA/UM",
        "publisher": "ZA/UM",
        "playtime_minutes": 1800,
        "source_scores": [
            {"source": "Metacritic", "score": 92, "scale": 100, "status": "live", "review_count": 62},
            {"source": "OpenCritic", "score": 92, "scale": 100, "status": "live", "review_count": 88},
            {"source": "Steam", "score": 93, "scale": 100, "status": "live", "review_count": 68000},
        ],
    },
    {
        "title": "Hi-Fi Rush",
        "slug": "hi-fi-rush",
        "summary": "A rhythm-action brawler where attacks, dodges, enemy patterns, and environmental motion all snap to the beat. It wraps character-action timing in a bright Saturday-morning-rock-band tone, rewarding stylish play without making rhythm mastery feel punishing for newcomers.",
        "cover_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/co5uzm.jpg",
        "release_date": date(2023, 1, 25),
        "release_year": 2023,
        "metrix_score": 88.7,
        "critic_score": 89.0,
        "user_score": 91.0,
        "genres": ["Action", "Rhythm", "Adventure"],
        "platforms": ["PC", "PlayStation 5", "Xbox Series X/S"],
        "developer": "Tango Gameworks",
        "publisher": "Bethesda Softworks",
        "playtime_minutes": 660,
        "source_scores": [
            {"source": "Metacritic", "score": 89, "scale": 100, "status": "live", "review_count": 58},
            {"source": "OpenCritic", "score": 88, "scale": 100, "status": "live", "review_count": 84},
            {"source": "Steam", "score": 96, "scale": 100, "status": "live", "review_count": 52000},
        ],
    },
]


def seed_games(db: Session) -> None:
    for game_data in SEED_GAMES:
        game = db.scalar(select(Game).where(Game.slug == game_data["slug"]))
        if game is None:
            db.add(Game(**game_data))
            continue

        for key, value in game_data.items():
            setattr(game, key, value)

    db.commit()
