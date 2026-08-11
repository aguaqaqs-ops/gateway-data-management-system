"""Negative mypy probe for VersionedFixtureConsumerClient typing coverage."""

from __future__ import annotations

from support.versioned_fixture_consumer import VersionedFixtureConsumerClient


def _negative_probe(client: VersionedFixtureConsumerClient) -> None:
    client.no_such_method()
