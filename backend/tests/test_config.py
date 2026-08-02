from zeromind.shared.config import Settings


def test_rsshub_private_hostnames_are_normalized() -> None:
    settings = Settings(
        _env_file=None,
        rsshub_private_hosts=" RSSHub, rsshub.,,SECONDARY ",
    )

    assert settings.rsshub_private_hostnames == frozenset({"rsshub", "secondary"})


def test_rsshub_private_hostnames_default_to_empty() -> None:
    settings = Settings(_env_file=None)

    assert settings.rsshub_private_hostnames == frozenset()
