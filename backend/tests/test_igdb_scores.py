from app.integrations.igdb_scores import build_igdb_scores_query, parse_igdb_scores


def test_igdb_score_query_batches_known_ids() -> None:
    query = build_igdb_scores_query([9, 2, 9, 0, -1])

    assert "where id = (2,9)" in query
    assert "limit 2" in query


def test_igdb_score_parser_keeps_only_valid_ratings() -> None:
    scores = parse_igdb_scores(
        [
            {"id": 2, "rating": 81.25, "rating_count": 47, "slug": "two"},
            {"id": 9, "aggregated_rating": 72, "aggregated_rating_count": 5},
            {"id": 10},
            {"id": 11, "rating": 101},
        ]
    )

    assert set(scores) == {2, 9}
    assert scores[2].score == 81.2
    assert scores[2].review_count == 47
    assert scores[9].score == 72
