"""Provider fact semantics and entity boundaries, without external traffic."""
import json
import pytest

from scripts.providers.two_gis import parse_html


URL = "https://2gis.kz/astana/firm/70000001018608940"


def card(*, center="71.469471,51.118023", headline="Национальный музей РК", rating="5"):
    return f'''<html><head>
      <meta property="og:title" content="{headline} на карте, Музеи, Астана — 2ГИС">
      <meta property="og:description" content="Оценка {rating}, 3691 фото, 2370 отзывов.">
      <meta property="og:image" content="https://beautyshare.2gis.ru/api/v1/image?center={center}&amp;desc=Тауелсиздик%2C%2054%3Cbr%20%2F%3EАстана">
    </head><body><h1>{headline}</h1><span>{rating}</span><span>16 270 оценок</span>
      <span>Контакты</span><span>Инфо</span><span>Отзывы</span><span>2371</span>
      <span>Фото</span><span>3692</span>
      <script>const ignored = {{secret:"never-copy", review:"review prose"}};
      const cover="https://i9.photo.2gis.com/main/branch/68/70000001018608940/common";
      const unrelated="https://i9.photo.2gis.com/main/branch/68/70000009999999999/common";</script>
    </body></html>'''


def test_rating_votes_text_reviews_and_photo_tabs_are_different_observations():
    row, = parse_html(card(), URL)
    assert row["rating"] == 5 and row["rating_count"] == 16270
    assert row["review_count"] == 2371
    assert row["lat"] == 51.118023 and row["lon"] == 71.469471
    assert row["address"] == "Тауелсиздик, 54 Астана"
    assert "visible_review_count_differs_from_open_graph" in row["warnings"]
    assert "visible_photo_count_differs_from_open_graph" in row["warnings"]


def test_only_exact_branch_cover_and_public_tabs_are_retained():
    row, = parse_html(card(), URL)
    assert row["photo_source_links"] == [URL + "/tab/photos", "https://i9.photo.2gis.com/main/branch/68/70000001018608940/common"]
    assert row["review_source_links"] == [URL + "/tab/reviews"]
    assert "never-copy" not in repr(row) and "review prose" not in repr(row)
    assert row["import_policy"] == "evaluation_only" and row["matched_poi_ids"] == []


def test_no_search_branch_aggregation_or_unrelated_domain_is_parsed():
    assert parse_html(card(), "https://2gis.kz/astana/branches/70000001018608940") == []
    assert parse_html(card(), "https://unrelated.example/astana/firm/70000001018608940") == []
    assert parse_html(card(), "https://2gis.kz.evil.example/astana/firm/70000001018608940") == []
    assert parse_html(card(), "https://user:secret@2gis.kz/astana/firm/70000001018608940") == []
    assert parse_html(card(), "https://2gis.kz:invalid/astana/firm/70000001018608940") == []


def test_challenge_or_missing_primary_identity_cannot_become_place():
    assert parse_html('<title>2GIS Captcha</title>' + card(), URL) == []
    assert parse_html(card().replace("<h1>", "<div>").replace("</h1>", "</div>"), URL) == []
    assert parse_html(card().replace("Национальный музей РК на карте", "Different firm on map"), URL) == []


def test_foreign_coordinates_and_nonfinite_values_are_not_accepted():
    assert parse_html(card(center="37.6,55.7"), URL)[0]["lat"] is None
    assert parse_html(card(center="nan,inf"), URL)[0]["lon"] is None
    assert parse_html(card(rating="6.5"), URL)[0]["rating"] is None


def test_visible_rating_wins_over_stale_metadata_and_query_is_not_retained():
    html = card().replace("Оценка 5,", "Оценка 4.9,")
    row, = parse_html(html, URL + "/tab/info?tracking=private")
    assert row["rating"] == 5 and row["source_url"] == URL
    assert "visible_rating_differs_from_open_graph" in row["warnings"]


def test_cached_html_reparse_preserves_original_acquisition_time():
    acquired = "2024-01-02T03:04:05+06:00"
    original = parse_html(card(), URL, observed_at=acquired)[0]
    replay = parse_html(card(), URL, observed_at=acquired)[0]
    assert original["observed_at"] == replay["observed_at"] == acquired
    assert not any("acquisition time is unknown" in warning for warning in replay["warnings"])


def test_cached_html_without_acquisition_metadata_remains_unknown():
    row = parse_html(card(), URL)[0]
    assert row["observed_at"] is None
    assert any("Original acquisition time is unknown" in warning for warning in row["warnings"])


def test_local_html_cli_requires_original_acquisition_and_preserves_it(monkeypatch, tmp_path):
    from scripts.providers.two_gis import main
    cached, output = tmp_path / "cached.html", tmp_path / "rows.json"
    cached.write_text(card())
    arguments = ["two_gis", "--html", str(cached), "--url", URL, "--out", str(output)]
    monkeypatch.setattr("sys.argv", arguments)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and not output.exists()
    acquired = "2024-01-02T03:04:05Z"
    monkeypatch.setattr("sys.argv", arguments + ["--observed-at", acquired])
    main()
    assert json.loads(output.read_text())[0]["observed_at"] == acquired
