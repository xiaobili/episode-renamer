from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TmdbSearchItem(BaseModel):
    tv_id: int
    name: str = ""
    original_name: str = ""
    year: Optional[int] = None


class TmdbEpisode(BaseModel):
    episode_number: int
    name: str = ""
    overview: str = ""
    air_date: Optional[str] = None
    rating: Optional[float] = None
    tmdb_id: Optional[int] = None


class TmdbSeason(BaseModel):
    season_number: int
    name: str = ""
    overview: str = ""
    air_date: Optional[str] = None
    tmdb_id: Optional[int] = None
    episodes: dict[int, TmdbEpisode] = Field(default_factory=dict)


class TmdbShow(BaseModel):
    tv_id: int
    name: str = ""
    original_name: str = ""
    year: Optional[int] = None
    overview: str = ""
    rating: Optional[float] = None
    votes: Optional[int] = None
    genres: list[str] = Field(default_factory=list)
    premiered: Optional[str] = None
    status: str = ""
