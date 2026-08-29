"""Publisher-grounded aggregation of OFAC primary and relation evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from black_meridian.ofac.contracts import (
    OfacPrimaryRecord,
    OfacSourceKey,
)
from black_meridian.ofac.relations import (
    OfacAddressRecord,
    OfacAliasRecord,
)

OfacPrimaryRecordKey = tuple[
    OfacSourceKey,
    str,
]

_PRIMARY_SOURCE_ORDER: dict[
    OfacSourceKey,
    int,
] = {
    "ofac_sdn_csv": 0,
    "ofac_consolidated_csv": 1,
}


class OfacAggregationError(ValueError):
    """Raised when publisher-grounded OFAC relations cannot be aggregated safely."""


class OfacEntityEvidence(BaseModel):
    """One primary OFAC occurrence with publisher-linked relation evidence."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    primary: OfacPrimaryRecord

    addresses: tuple[
        OfacAddressRecord,
        ...,
    ] = ()

    aliases: tuple[
        OfacAliasRecord,
        ...,
    ] = ()

    @model_validator(mode="after")
    def validate_publisher_grounded_relations(
        self,
    ) -> Self:
        """Require every attached relation to point to this exact primary occurrence."""

        parent_key = self.primary.source_record_key

        seen_address_keys: set[tuple[str, str]] = set()

        for address in self.addresses:
            if address.parent_record_key != parent_key:
                raise ValueError(
                    "OFAC address relation does not point to the aggregate primary record."
                )

            address_key = address.source_record_key

            if address_key in seen_address_keys:
                raise ValueError(
                    "OFAC entity evidence contains duplicate address relation identity."
                )

            seen_address_keys.add(address_key)

        seen_alias_keys: set[tuple[str, str]] = set()

        for alias in self.aliases:
            if alias.parent_record_key != parent_key:
                raise ValueError(
                    "OFAC alias relation does not point to the aggregate primary record."
                )

            alias_key = alias.source_record_key

            if alias_key in seen_alias_keys:
                raise ValueError("OFAC entity evidence contains duplicate alias relation identity.")

            seen_alias_keys.add(alias_key)

        return self

    @property
    def source_record_key(
        self,
    ) -> OfacPrimaryRecordKey:
        """Return the source-scoped identity of the primary evidence occurrence."""

        return self.primary.source_record_key

    @property
    def address_count(
        self,
    ) -> int:
        """Return publisher-linked address count."""

        return len(self.addresses)

    @property
    def alias_count(
        self,
    ) -> int:
        """Return publisher-linked alias count."""

        return len(self.aliases)


def build_ofac_entity_evidence(
    primary_records: tuple[
        OfacPrimaryRecord,
        ...,
    ],
    address_records: tuple[
        OfacAddressRecord,
        ...,
    ] = (),
    alias_records: tuple[
        OfacAliasRecord,
        ...,
    ] = (),
) -> tuple[
    OfacEntityEvidence,
    ...,
]:
    """Attach publisher-defined relations to source-scoped primary evidence."""

    if not primary_records:
        raise OfacAggregationError(
            "OFAC aggregation requires at least one primary publisher record."
        )

    primary_by_key: dict[
        OfacPrimaryRecordKey,
        OfacPrimaryRecord,
    ] = {}

    for primary in primary_records:
        primary_key = primary.source_record_key

        if primary_key in primary_by_key:
            raise OfacAggregationError(
                "OFAC aggregation contains duplicate "
                "primary source-record identity: "
                f"{primary_key!r}."
            )

        primary_by_key[primary_key] = primary

    addresses_by_parent: defaultdict[
        OfacPrimaryRecordKey,
        list[OfacAddressRecord],
    ] = defaultdict(list)

    seen_address_keys: set[tuple[str, str]] = set()

    for address in address_records:
        relation_key = address.source_record_key

        if relation_key in seen_address_keys:
            raise OfacAggregationError(
                "OFAC aggregation contains duplicate "
                "address source-record identity: "
                f"{relation_key!r}."
            )

        seen_address_keys.add(relation_key)

        parent_key = address.parent_record_key

        if parent_key not in primary_by_key:
            raise OfacAggregationError(
                f"OFAC address relation references a missing primary parent: {parent_key!r}."
            )

        addresses_by_parent[parent_key].append(address)

    aliases_by_parent: defaultdict[
        OfacPrimaryRecordKey,
        list[OfacAliasRecord],
    ] = defaultdict(list)

    seen_alias_keys: set[tuple[str, str]] = set()

    for alias in alias_records:
        relation_key = alias.source_record_key

        if relation_key in seen_alias_keys:
            raise OfacAggregationError(
                "OFAC aggregation contains duplicate "
                "alias source-record identity: "
                f"{relation_key!r}."
            )

        seen_alias_keys.add(relation_key)

        parent_key = alias.parent_record_key

        if parent_key not in primary_by_key:
            raise OfacAggregationError(
                f"OFAC alias relation references a missing primary parent: {parent_key!r}."
            )

        aliases_by_parent[parent_key].append(alias)

    ordered_primaries = sorted(
        primary_records,
        key=lambda primary: (
            _PRIMARY_SOURCE_ORDER[primary.source_key],
            int(primary.publisher_record_id),
        ),
    )

    aggregates: list[OfacEntityEvidence] = []

    for primary in ordered_primaries:
        primary_key = primary.source_record_key

        ordered_addresses = tuple(
            sorted(
                addresses_by_parent[primary_key],
                key=lambda address: int(address.publisher_relation_id),
            )
        )

        ordered_aliases = tuple(
            sorted(
                aliases_by_parent[primary_key],
                key=lambda alias: int(alias.publisher_relation_id),
            )
        )

        aggregates.append(
            OfacEntityEvidence(
                primary=primary,
                addresses=ordered_addresses,
                aliases=ordered_aliases,
            )
        )

    return tuple(aggregates)
