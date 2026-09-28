"""直接调用解析器也必须遵守资源与安全边界，不只依赖 HTTP 限制。"""

import pytest

from subscription_service.application.opml_errors import InvalidOpmlError, OpmlTooLargeError
from subscription_service.infrastructure.opml.reader import SafeOpmlReader


def test_byte_limit_accepts_boundary_and_rejects_extra_byte():
    reader = SafeOpmlReader()
    template = b"<opml><body/></opml>"
    boundary = template + b" " * (1024 * 1024 - len(template))
    assert reader.parse(boundary) == ()
    with pytest.raises(OpmlTooLargeError):
        reader.parse(boundary + b" ")


def test_outline_limit_accepts_1000_folders_but_rejects_1001():
    reader = SafeOpmlReader()
    assert reader.parse(b"<opml><body>" + b"<outline/>" * 1000 + b"</body></opml>") == ()
    with pytest.raises(InvalidOpmlError):
        reader.parse(b"<opml><body>" + b"<outline/>" * 1001 + b"</body></opml>")


def test_depth_limit_applies_to_head_as_well_as_body():
    reader = SafeOpmlReader()
    assert (
        reader.parse(b"<opml><body>" + b"<outline>" * 30 + b"</outline>" * 30 + b"</body></opml>")
        == ()
    )
    with pytest.raises(InvalidOpmlError):
        reader.parse(b"<opml><head>" + b"<x>" * 31 + b"</x>" * 31 + b"</head><body/></opml>")


def test_non_outline_nodes_are_counted_to_bound_head_complexity():
    with pytest.raises(InvalidOpmlError):
        SafeOpmlReader().parse(b"<opml><head>" + b"<x/>" * 10000 + b"</head><body/></opml>")


def test_utf16_entity_declaration_cannot_bypass_xml_protection():
    xml = """<?xml version="1.0" encoding="UTF-16"?>
        <!DOCTYPE opml [<!ENTITY x "secret">]>
        <opml><body><outline text="&x;" xmlUrl="https://example.com/feed"/></body></opml>"""
    with pytest.raises(InvalidOpmlError):
        SafeOpmlReader().parse(xml.encode("utf-16"))
