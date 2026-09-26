from app.core.nfo_writer import build_nfo_decisions
from app.models.nfo import NfoEntry, NfoOptions
from app.models.tmdb import TmdbEpisode, TmdbSeason, TmdbShow


def test_preview_shows_resolvable_show_level_paths():
    """预览必须能报出剧集级 NFO 的落点, 否则用户看不到 tvshow.nfo 写到哪了 ——
    库根污染的唯一防线就是「让他看见」。"""
    entries = [
        NfoEntry(
            file_id="f1",
            new_path="/media/绝命毒师/Season 02/绝命毒师 - S02E05.mkv",
            show_name="绝命毒师",
            season=2,
            episode=5,
            show=TmdbShow(tv_id=1396, name="绝命毒师", original_name="Breaking Bad", year=2008),
            season_data=TmdbSeason(season_number=2, name="第 2 季", tmdb_id=3575),
            episode_data=TmdbEpisode(episode_number=5, name="Breakage", tmdb_id=62085),
        )
    ]
    decisions = build_nfo_decisions(entries, NfoOptions(enabled=True))

    paths = {d.kind: d.path for d in decisions}
    assert paths["episode"] == "/media/绝命毒师/Season 02/绝命毒师 - S02E05.nfo"
    assert paths["season"] == "/media/绝命毒师/Season 02/season.nfo"
    assert paths["tvshow"] == "/media/绝命毒师/tvshow.nfo"
