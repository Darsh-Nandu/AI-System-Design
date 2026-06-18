"""Unit tests for deterministic document ID generation."""

from __future__ import annotations

from datetime import date

from rag.indexing.document_id import (
    base_id_without_version,
    bump_version,
    make_chunk_id,
    make_document_id,
)
from rag.models import DocType, RawDocument


def _doc(**kwargs) -> RawDocument:
    defaults = dict(
        country_code="IN",
        state_code="MH",
        district_code="MUM",
        year=2019,
        doc_type=DocType.CASE_LAW,
        serial="4821",
        name="Test Case",
        date=date(2019, 3, 14),
        text="...",
        version=1,
    )
    defaults.update(kwargs)
    return RawDocument(**defaults)


def test_document_id_format() -> None:
    doc_id = make_document_id(_doc())
    assert doc_id == "IN:MH:MUM:2019:CR:4821:v1"


def test_document_id_is_deterministic() -> None:
    a = make_document_id(_doc())
    b = make_document_id(_doc())
    assert a == b


def test_version_in_id() -> None:
    doc_id = make_document_id(_doc(version=3))
    assert doc_id.endswith(":v3")


def test_doc_type_codes() -> None:
    assert "ST" in make_document_id(_doc(doc_type=DocType.STATUTE))
    assert "RG" in make_document_id(_doc(doc_type=DocType.REGULATION))


def test_make_chunk_id() -> None:
    cid = make_chunk_id("IN:MH:MUM:2019:CR:4821:v1", 42)
    assert cid == "IN:MH:MUM:2019:CR:4821:v1:0042"


def test_base_id_without_version() -> None:
    doc_id = "IN:MH:MUM:2019:CR:4821:v2"
    assert base_id_without_version(doc_id) == "IN:MH:MUM:2019:CR:4821"


def test_bump_version() -> None:
    assert bump_version("IN:MH:MUM:2019:CR:4821:v1") == "IN:MH:MUM:2019:CR:4821:v2"
    assert bump_version("IN:MH:MUM:2019:CR:4821:v9") == "IN:MH:MUM:2019:CR:4821:v10"
