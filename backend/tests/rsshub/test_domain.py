import pytest

from zeromind.rsshub.domain import RSSHubInstance, normalize_instance_base_url


def test_instance_base_url_is_normalized() -> None:
    assert (
        normalize_instance_base_url("HTTPS://RSS.EXAMPLE.COM:443/prefix/")
        == "https://rss.example.com/prefix"
    )


@pytest.mark.parametrize(
    "value",
    [
        "rsshub://twitter/user/vista8",
        "ftp://rsshub.example.com",
        "https://user:secret@rsshub.example.com",
        "https://rsshub.example.com?key=secret",
        "https://rsshub.example.com/#fragment",
    ],
)
def test_instance_base_url_rejects_non_server_addresses(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_instance_base_url(value)


def test_instance_requires_a_name() -> None:
    with pytest.raises(ValueError, match="name"):
        RSSHubInstance.create(name=" ", base_url="https://rsshub.example.com")
