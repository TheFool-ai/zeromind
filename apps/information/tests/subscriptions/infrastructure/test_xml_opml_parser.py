import pytest

from zeromind.subscriptions.application.exceptions.invalid_opml_error import InvalidOpmlError
from zeromind.subscriptions.infrastructure.opml.xml_opml_parser import XmlOpmlParser


def test_preview_opml_reads_nested_categories_and_deduplicates_urls() -> None:
    data = b"""<?xml version="1.0"?>
    <opml version="2.0">
      <head><title>My feeds</title></head>
      <body>
        <outline text="Technology">
          <outline text="Example" title="Example Feed"
                   type="rss" xmlUrl="https://example.com/feed.xml"
                   htmlUrl="https://example.com"/>
          <outline text="Duplicate"
                   xmlUrl="HTTPS://EXAMPLE.COM:443/feed.xml#fragment"/>
        </outline>
      </body>
    </opml>"""

    result = XmlOpmlParser().preview(data)

    assert result.title == "My feeds"
    assert len(result.entries) == 1
    assert result.entries[0].title == "Example Feed"
    assert result.entries[0].feed_url == "https://example.com/feed.xml"
    assert result.entries[0].site_url == "https://example.com"
    assert result.entries[0].categories == ("Technology",)
    assert result.duplicate_count == 1


def test_preview_opml_rejects_external_entities() -> None:
    data = b"""<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <opml version="2.0"><body>
      <outline text="&xxe;" xmlUrl="https://example.com/feed.xml"/>
    </body></opml>"""

    with pytest.raises(InvalidOpmlError):
        XmlOpmlParser().preview(data)


def test_preview_opml_reports_invalid_feed_urls_without_aborting_batch() -> None:
    data = b"""<opml version="1.0"><body>
      <outline text="Good" xmlUrl="https://example.com/feed"/>
      <outline text="Bad" xmlUrl="ftp://example.com/feed"/>
    </body></opml>"""

    result = XmlOpmlParser().preview(data)

    assert [entry.title for entry in result.entries] == ["Good"]
    assert result.invalid_entries[0].title == "Bad"
    assert result.invalid_entries[0].reason == "invalid_feed_url"


def test_preview_opml_accepts_rsshub_locator_extension() -> None:
    data = b"""<opml version="2.0"><body>
      <outline text="Vista8"
               xmlUrl="rsshub://twitter/user/vista8?mode=full"/>
    </body></opml>"""

    result = XmlOpmlParser().preview(data)

    assert result.invalid_entries == ()
    assert result.entries[0].feed_url == "rsshub://twitter/user/vista8?mode=full"
