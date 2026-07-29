"""Shared lightweight ORM loading policy for catalog/card responses."""

from sqlalchemy.orm import Load, load_only, noload, selectinload

from ..models import Game


CATALOG_GAME_COLUMNS = (
    Game.id,
    Game.title,
    Game.slug,
    Game.summary_short,
    Game.cover_url,
    Game.release_date,
    Game.release_year,
    Game.image_url,
    Game.ratings_refreshed_at,
    Game.metadata_refreshed_at,
    Game.prices_refreshed_at,
    Game.content_type,
    Game.metrix_score,
    Game.rank_score,
    Game.is_rankable,
    Game.seo_updated_at,
    Game.genres,
    Game.platforms,
    Game.source_scores,
    Game.developer,
    Game.publisher,
    Game.steam_app_id,
    Game.playtime_minutes,
    Game.hltb_url,
    Game.hltb_main_story_minutes,
    Game.hltb_main_extra_minutes,
    Game.hltb_completionist_minutes,
    Game.hltb_all_styles_minutes,
    Game.is_endless,
    Game.proton_tier,
    Game.proton_score,
    Game.award_count,
    Game.award_nominations,
    Game.goty_year,
    Game.awards,
)


def catalog_load_options(*, include_prices: bool) -> tuple[Load, ...]:
    price_option = (
        selectinload(Game.price_snapshots)
        if include_prices
        else noload(Game.price_snapshots)
    )
    return (
        load_only(*CATALOG_GAME_COLUMNS, raiseload=True),
        price_option,
    )
