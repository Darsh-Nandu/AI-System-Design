"""Unit tests for metadata pre-filter builder."""

from __future__ import annotations

from datetime import date

from rag.retrieval.metadata_filter import build_card_filter, extract_filters_from_sub_query


def test_empty_filter_returns_empty_dict() -> None:
    f = build_card_filter()
    assert f == {}


def test_jurisdiction_filter() -> None:
    f = build_card_filter(jurisdiction=["IN", "MH"])
    assert f["jurisdiction"] == ["IN", "MH"]


def test_doc_type_filter() -> None:
    f = build_card_filter(doc_type="case_law")
    assert f["doc_type"] == "case_law"


def test_date_range_filter() -> None:
    f = build_card_filter(date_from=date(2018, 1, 1), date_to=date(2020, 12, 31))
    assert f["date"]["gte"] == "2018-01-01"
    assert f["date"]["lte"] == "2020-12-31"


def test_date_from_only() -> None:
    f = build_card_filter(date_from=date(2019, 6, 1))
    assert "gte" in f["date"]
    assert "lte" not in f["date"]


def test_combined_filters() -> None:
    f = build_card_filter(
        jurisdiction=["IN"],
        doc_type="statute",
        tags=["data_breach"],
    )
    assert "jurisdiction" in f
    assert "doc_type" in f
    assert "tags" in f


def test_extract_string_jurisdiction_to_list() -> None:
    f = extract_filters_from_sub_query({"jurisdiction": "IN"})
    assert f["jurisdiction"] == ["IN"]
