"""经真实 HTTP 协议层和临时迁移数据库验证管理闭环，不模拟仓储。"""

from uuid import uuid4

import pytest

PREFIX = "/api/v1/subscriptions"


async def create(api, **changes):
    return await api.post(
        PREFIX,
        json={
            "name": " 新闻 ",
            "feed_address": "HTTPS://EXAMPLE.com:443/feed",
            "categories": [" 技术 ", "技术"],
            **changes,
        },
    )


async def test_create_detail_patch_disable_enable_persist_across_requests(api):
    response = await create(api)
    assert response.status_code == 201
    data = response.json()
    path = f"{PREFIX}/{data['id']}"
    assert response.headers["location"] == path
    assert data["name"] == "新闻" and data["categories"] == ["技术"]
    assert data["feed_address"] == "https://example.com/feed"
    assert "site_url" not in data
    assert (await api.get(path)).json() == data
    changed = await api.patch(
        path, json={"name": "新名称", "categories": [], "expected_configuration_version": 1}
    )
    assert changed.status_code == 200
    assert changed.json()["configuration_version"] == 2
    assert changed.json()["feed_address"] == data["feed_address"]
    assert changed.json()["categories"] == []
    closed = await api.post(path + "/disable")
    assert closed.status_code == 200 and closed.json()["enabled"] is False
    repeated = await api.post(path + "/disable")
    assert repeated.json() == closed.json()
    enabled = await api.post(path + "/enable", json={"expected_configuration_version": 3})
    assert enabled.status_code == 200 and enabled.json()["enabled"] is True
    assert (await api.get(path)).json() == enabled.json()


async def test_duplicate_creation_returns_409_and_does_not_add_row(api):
    await create(api)
    duplicate = await create(api, feed_address="https://example.com/feed#part")
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "subscription_already_exists"
    assert len((await api.get(PREFIX)).json()["items"]) == 1


async def test_failed_address_change_rolls_back_name_change(api):
    first = (await create(api)).json()
    await create(api, feed_address="https://second.example/feed")
    path = f"{PREFIX}/{first['id']}"
    failed = await api.patch(
        path, json={"name": "不应保存", "feed_address": "https://second.example/feed"}
    )
    assert failed.status_code == 409
    assert (await api.get(path)).json() == first
    success = await api.patch(path, json={"feed_address": "rsshub://Twitter/User/example"})
    assert success.status_code == 200 and success.json()["address_version"] == 2


async def test_stale_version_returns_conflict_without_changing_data(api):
    initial = (await create(api)).json()
    path = f"{PREFIX}/{initial['id']}"
    changed = await api.patch(path, json={"name": "已改名"})
    for method, suffix, body in [
        ("PATCH", "", {"name": "过期", "expected_configuration_version": 1}),
        ("POST", "/disable", {"expected_configuration_version": 1}),
    ]:
        response = await api.request(method, path + suffix, json=body)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "subscription_version_conflict"
    assert (await api.get(path)).json() == changed.json()


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"name": "x" * 301},
        {"feed_address": "ftp://example.com"},
        {"feed_address": "https://user:private-secret@example.com/feed"},
        {"categories": ["x" * 161]},
        {"categories": "wrong"},
        {"site_url": "https://example.com"},
        {"enabled": False},
        {"name": None},
    ],
)
async def test_create_rejects_invalid_fields_without_leaking_input(api, changes):
    response = await create(api, **changes)
    assert response.status_code == 422
    assert "private-secret" not in response.text
    assert (await api.get(PREFIX)).json()["items"] == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"categories": None},
        {"feed_address": None},
        {"enabled": False},
        {"expected_configuration_version": 0},
    ],
)
async def test_patch_rejects_ambiguous_or_unknown_fields(api, body):
    initial = (await create(api)).json()
    path = f"{PREFIX}/{initial['id']}"
    assert (await api.patch(path, json=body)).status_code == 422
    assert (await api.get(path)).json() == initial


async def test_missing_source_and_invalid_id_have_distinct_errors(api):
    path = f"{PREFIX}/{uuid4()}"
    for method, suffix, body in [
        ("GET", "", None),
        ("PATCH", "", {"name": "x"}),
        ("POST", "/enable", None),
        ("POST", "/disable", None),
    ]:
        response = await api.request(method, path + suffix, json=body)
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "subscription_not_found"
    assert (await api.get(PREFIX + "/not-a-uuid")).status_code == 422


async def test_list_filter_pagination_and_query_validation(api):
    first = (await create(api)).json()
    await create(api, feed_address="https://second.example/feed")
    await api.post(f"{PREFIX}/{first['id']}/disable")
    disabled = await api.get(PREFIX, params={"enabled": "false"})
    assert [row["id"] for row in disabled.json()["items"]] == [first["id"]]
    page1 = (await api.get(PREFIX, params={"limit": 1})).json()
    page2 = (await api.get(PREFIX, params={"limit": 1, "offset": 1})).json()
    assert page1["items"][0]["id"] != page2["items"][0]["id"]
    for query in [{"limit": 0}, {"limit": 1001}, {"offset": -1}, {"enabled": "unknown"}]:
        assert (await api.get(PREFIX, params=query)).status_code == 422


async def test_noop_patch_does_not_change_configuration_version(api):
    initial = (await create(api)).json()
    response = await api.patch(f"{PREFIX}/{initial['id']}", json={"name": " 新闻 "})
    assert response.status_code == 200 and response.json() == initial


async def test_openapi_exposes_management_contract(api):
    response = await api.get("/api/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "post" in paths[PREFIX] and "get" in paths[PREFIX]
    assert "patch" in paths[PREFIX + "/{subscription_id}"]
