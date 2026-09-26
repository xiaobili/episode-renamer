import pytest
from fastapi.testclient import TestClient

from app.api.renamer import cache_files
from app.main import app
from app.models.file import FileInfo

TEMPLATE = "{show} - S{season_padded}E{episode_padded}{extension}"

# 用 overrides 钉死解析结果, 让断言不依赖文件名解析器的行为
OVERRIDES = {"f1": {"show_name": "Test Show", "season": 1, "episode": 2}}


@pytest.fixture
def client():
    cache_files([
        FileInfo(
            id="f1",
            source="local",
            path="/media/Test Show/Test.Show.S01E02.mkv",
            filename="Test.Show.S01E02.mkv",
            extension=".mkv",
            parent_dir="/media/Test Show",
        )
    ])
    return TestClient(app)


def preview(client, **extra):
    payload = {
        "file_ids": ["f1"],
        "template": TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "overrides": OVERRIDES,
    }
    payload.update(extra)
    res = client.post("/api/rename/preview", json=payload)
    assert res.status_code == 200, res.text
    return res.json()["results"][0]


def test_omitting_pad_fields_preserves_current_behaviour(client):
    # Review Focus 4: 老客户端不传 pad, 行为必须与改动前逐字节一致
    row = preview(client)
    assert row["new_filename"] == "Test Show - S01E02.mkv"


def test_episode_pad_digits_is_honoured(client):
    row = preview(client, episode_pad_digits=3)
    assert row["new_filename"] == "Test Show - S01E002.mkv"


def test_season_pad_digits_is_honoured(client):
    row = preview(client, season_pad_digits=3)
    assert row["new_filename"] == "Test Show - S001E02.mkv"


def test_episode_only_does_not_disturb_season(client):
    # Review Focus 3: 只传一个字段时, 另一个退回全局默认
    row = preview(client, episode_pad_digits=4)
    assert row["new_filename"] == "Test Show - S01E0002.mkv"


def test_zero_is_clamped_to_one(client):
    # Review Focus 1: 用户清空数字框留下 0
    row = preview(client, episode_pad_digits=0, season_pad_digits=0)
    assert row["new_filename"] == "Test Show - S1E2.mkv"


def test_negative_is_clamped_to_one(client):
    # Review Focus 1: str(-1).zfill(2) == "-1" 会产出损坏文件名
    row = preview(client, episode_pad_digits=-1, season_pad_digits=-1)
    assert row["new_filename"] == "Test Show - S1E2.mkv"


def test_oversized_is_clamped_to_six(client):
    # Review Focus 2: 输入 99 不应生成 99 位补零
    row = preview(client, episode_pad_digits=99, season_pad_digits=99)
    assert row["new_filename"] == "Test Show - S000001E000002.mkv"


def test_folder_template_honours_pad(client):
    row = preview(
        client,
        folder_template="Season {season_padded}",
        create_season_folder=True,
        season_pad_digits=3,
    )
    assert row["new_path"] == "/media/Test Show/Season 001/Test Show - S001E02.mkv"


def test_execute_route_accepts_pad_fields(client):
    # 干跑, 不触盘; 只验证请求模型接受字段且不报 422
    payload = {
        "file_ids": ["f1"],
        "template": TEMPLATE,
        "source": "local",
        "path": "/media/Test Show",
        "overrides": OVERRIDES,
        "conflict_strategy": "skip",
        "episode_pad_digits": 3,
        "season_pad_digits": 3,
    }
    res = client.post("/api/rename/dry-run", json=payload)
    assert res.status_code == 200, res.text
