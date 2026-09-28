"""验证 OPML 真实导入和已存在跳过，不用模拟替代数据库副作用。"""

import asyncio

import pytest
from sqlalchemy import text

PREFIX = "/api/v1/subscriptions"
IMPORT = PREFIX + "/import/opml"


async def upload(api, outlines, **kwargs):
    return await api.post(
        IMPORT,
        content=f'<opml version="2.0"><body>{outlines}</body></opml>'.encode(),
        headers={"Content-Type": "application/xml"},
        **kwargs,
    )


async def test_import_maps_nested_categories_and_reimport_skips_existing(api):
    xml = """<outline text="技术"><outline text="Python">
      <outline title=" 新闻 " text="备用" xmlUrl="HTTPS://EXAMPLE.com:443/feed"
               category="Python, 资讯" htmlUrl="https://example.com"/>
      <outline type="rss" xmlUrl="rsshub://Twitter/User/example"/>
    </outline></outline>"""
    response = await upload(api, xml)
    assert response.status_code == 200
    result = response.json()
    assert (result["total"], result["created"], result["skipped"], result["failed"]) == (2, 2, 0, 0)
    assert result["remaining"] == 0
    items = (await api.get(PREFIX)).json()["items"]
    assert items[0]["name"] == "新闻"
    assert items[0]["categories"] == ["技术", "Python", "资讯"]
    assert items[1]["name"] == "rsshub://Twitter/User/example"
    assert all(row["enabled"] is True for row in items)
    assert "site_url" not in items[0]
    repeated = (await upload(api, xml)).json()
    assert (repeated["created"], repeated["skipped"]) == (0, 2)
    assert (await api.get(PREFIX)).json()["items"] == items


async def test_existing_source_is_skipped_without_overwriting_or_reenabling(api):
    source = (
        await api.post(
            PREFIX,
            json={
                "name": "原名称",
                "feed_address": "https://example.com/feed",
                "categories": ["旧分类"],
            },
        )
    ).json()
    path = f"{PREFIX}/{source['id']}"
    original = (await api.post(path + "/disable")).json()
    # 已有地址优先跳过，甚至不尝试以新文件的非法长名称覆盖现有配置。
    result = (
        await upload(
            api, '<outline title="' + "x" * 301 + '" xmlUrl="HTTPS://EXAMPLE.com:443/feed#part"/>'
        )
    ).json()
    assert result["skipped"] == 1 and result["failed"] == 0
    assert result["items"][0]["code"] == "already_exists"
    assert (await api.get(path)).json() == original


async def test_file_duplicates_skip_and_invalid_entries_do_not_block_valid_ones(api):
    response = await upload(
        api,
        """
      <outline text="无效" xmlUrl="ftp://example.com/feed"/>
      <outline text="第一条" xmlUrl="https://example.com/feed"/>
      <outline text="不能覆盖" xmlUrl="HTTPS://EXAMPLE.com:443/feed#fragment"/>
      <outline type="rss" text="缺地址"/>
      <outline text="另一条" xmlUrl="https://second.example/feed"/>
      <outline type="link" text="网页" url="https://example.com"/>
    """,
    )
    assert response.status_code == 200
    result = response.json()
    assert (result["total"], result["created"], result["skipped"], result["failed"]) == (5, 2, 1, 2)
    assert [r["index"] for r in result["items"]] == [1, 2, 3, 4, 5]
    assert [r["status"] for r in result["items"]] == [
        "failed",
        "created",
        "skipped",
        "failed",
        "created",
    ]
    assert result["items"][2]["code"] == "duplicate_in_file"
    assert [r["name"] for r in (await api.get(PREFIX)).json()["items"]] == ["第一条", "另一条"]


async def test_invalid_first_occurrence_does_not_block_later_valid_same_address(api):
    response = await upload(
        api,
        '<outline title="'
        + "x" * 301
        + '" xmlUrl="https://example.com/feed"/>'
        + '<outline title="合法名称" xmlUrl="https://example.com/feed"/>',
    )
    result = response.json()
    assert (result["created"], result["skipped"], result["failed"]) == (1, 0, 1)
    assert (await api.get(PREFIX)).json()["items"][0]["name"] == "合法名称"


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"<opml><body>",
        b"<rss/>",
        b"<opml/>",
        b"<opml><body/><body/></opml>",
        b'<opml><body><outline xmlUrl="https://example.com/feed"/></body></opml>junk',
        b'<opml><body><wrong><outline xmlUrl="https://example.com/feed"/></wrong></body></opml>',
        b'<!DOCTYPE opml [<!ENTITY secret SYSTEM "file:///etc/passwd">]><opml><body>&secret;</body></opml>',
        b'<!DOCTYPE opml SYSTEM "https://example.com/evil.dtd"><opml><body/></opml>',
    ],
)
async def test_invalid_or_unsafe_document_is_rejected_before_any_write(api, body):
    response = await api.post(IMPORT, content=body, headers={"Content-Type": "application/xml"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_opml"
    assert (await api.get(PREFIX)).json()["items"] == []


@pytest.mark.parametrize(
    "outlines",
    [
        '<outline xmlUrl="https://example.com/feed"/>' * 1001,
        "<outline>" * 32 + '<outline xmlUrl="https://example.com/feed"/>' + "</outline>" * 32,
    ],
)
async def test_complexity_limits_reject_whole_document(api, outlines):
    response = await upload(api, outlines)
    assert response.status_code == 422
    assert (await api.get(PREFIX)).json()["items"] == []


async def test_streamed_size_limit_is_enforced_without_content_length(api):
    async def chunks():
        yield b"<opml><body>"
        for _ in range(17):
            yield b" " * 65536
        yield b"</body></opml>"

    response = await api.post(IMPORT, content=chunks(), headers={"Content-Type": "text/xml"})
    assert response.status_code == 413
    assert (await api.get(PREFIX)).json()["items"] == []


async def test_empty_valid_file_and_encoding_are_supported(api):
    empty = await upload(api, '<outline text="空目录"/>')
    assert empty.status_code == 200 and empty.json()["total"] == 0
    xml = '<?xml version="1.0" encoding="UTF-16"?><opml><body><outline text="中文" xmlUrl="https://example.com/feed"/></body></opml>'
    result = await api.post(
        IMPORT, content=xml.encode("utf-16"), headers={"Content-Type": "text/xml"}
    )
    assert result.status_code == 200 and result.json()["created"] == 1
    assert (await api.get(PREFIX)).json()["items"][0]["name"] == "中文"


async def test_errors_do_not_echo_credentials_and_non_xml_media_is_rejected(api):
    response = await upload(
        api,
        '<outline text="private-secret" xmlUrl="https://user:private-secret@example.com/feed"/>',
    )
    assert response.status_code == 200 and response.json()["failed"] == 1
    assert "private-secret" not in response.text
    wrong = await api.post(IMPORT, json={"content": "<opml/>"})
    assert wrong.status_code == 415


async def test_database_failure_reports_committed_progress_and_stops(api, api_database):
    # SQLite 触发器产生真实非唯一约束错误，验证没有吞成重复或成功。
    async with api_database.engine.begin() as conn:
        await conn.execute(
            text("""CREATE TRIGGER reject_import BEFORE INSERT ON subscriptions
            WHEN NEW.name = '拒绝' BEGIN SELECT RAISE(ABORT, 'storage failure'); END""")
        )
    response = await upload(
        api,
        """
        <outline text="已提交" xmlUrl="https://first.example/feed"/>
        <outline text="拒绝" xmlUrl="https://second.example/feed"/>
        <outline text="不应执行" xmlUrl="https://third.example/feed"/>
    """,
    )
    assert response.status_code == 503
    progress = response.json()["detail"]["result"]
    assert (progress["total"], progress["created"], progress["failed"], progress["remaining"]) == (
        3,
        1,
        1,
        1,
    )
    assert progress["items"][1]["code"] == "storage_error"
    assert [r["name"] for r in (await api.get(PREFIX)).json()["items"]] == ["已提交"]
    async with api_database.engine.begin() as conn:
        await conn.execute(text("DROP TRIGGER reject_import"))
    retried = await upload(
        api,
        """
        <outline text="不覆盖已提交" xmlUrl="https://first.example/feed"/>
        <outline text="拒绝" xmlUrl="https://second.example/feed"/>
        <outline text="不应执行" xmlUrl="https://third.example/feed"/>
    """,
    )
    assert retried.status_code == 200
    assert (retried.json()["created"], retried.json()["skipped"]) == (2, 1)
    assert (await api.get(PREFIX)).json()["items"][0]["name"] == "已提交"


async def test_openapi_describes_raw_xml_import(api):
    paths = (await api.get("/api/openapi.json")).json()["paths"]
    assert IMPORT in paths
    assert "application/xml" in paths[IMPORT]["post"]["requestBody"]["content"]


async def test_concurrent_import_unique_conflict_becomes_skip(api, monkeypatch):
    from subscription_service.infrastructure.persistence.subscription_repository import (
        SqlAlchemySubscriptionRepository,
    )

    original = SqlAlchemySubscriptionRepository.find_by_address
    both_read = asyncio.Event()
    readers = 0

    async def synchronized_read(self, address):
        nonlocal readers
        result = await original(self, address)
        readers += 1
        if readers == 2:
            both_read.set()
        await asyncio.wait_for(both_read.wait(), timeout=5)
        return result

    # 只同步真实 SELECT 之后的时间点，不模拟查重结果或数据库唯一约束。
    monkeypatch.setattr(SqlAlchemySubscriptionRepository, "find_by_address", synchronized_read)
    xml = '<outline text="来源" xmlUrl="https://example.com/feed"/>'
    first, second = await asyncio.gather(upload(api, xml), upload(api, xml))
    assert first.status_code == second.status_code == 200
    assert sorted([first.json()["created"], second.json()["created"]]) == [0, 1]
    assert sorted([first.json()["skipped"], second.json()["skipped"]]) == [0, 1]
    assert len((await api.get(PREFIX)).json()["items"]) == 1
