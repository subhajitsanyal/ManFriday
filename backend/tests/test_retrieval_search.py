from manfriday.retrieval import ChunkMetadata, SourceMetadata, build_keyword_index


def test_keyword_query_returns_matching_chunk() -> None:
    index = build_keyword_index(
        sources=(
            _source("notes", "local_file", "notes.txt"),
            _source("manual", "local_file", "manual.md", manual=True),
        ),
        chunks=(
            _chunk("notes", 0, "The small hex key belongs with the camera mount."),
            _chunk("manual", 0, "Charge batteries on a nonflammable surface."),
        ),
    )

    results = index.query("hex key")

    assert len(results) == 1
    assert results[0].source.uri == "notes.txt"
    assert results[0].chunk.text == "The small hex key belongs with the camera mount."
    assert results[0].score > 0


def test_keyword_query_searches_chunk_section_metadata() -> None:
    index = build_keyword_index(
        sources=(_source("manual", "local_file", "manual.md", manual=True),),
        chunks=(
            _chunk(
                "manual",
                0,
                "Clamp the workpiece before drilling.",
                section="Clamp Setup",
            ),
        ),
    )

    results = index.query("setup")

    assert len(results) == 1
    assert results[0].chunk.section == "Clamp Setup"


def test_keyword_query_ordering_is_stable_for_equal_scores() -> None:
    index = build_keyword_index(
        sources=(
            _source("source_b", "local_file", "b.md"),
            _source("source_a", "local_file", "a.md"),
        ),
        chunks=(
            _chunk("source_b", 1, "camera mount"),
            _chunk("source_a", 0, "camera mount"),
            _chunk("source_b", 0, "camera mount"),
        ),
    )

    first = index.query("camera")
    second = index.query("camera")

    assert [(item.source.uri, item.chunk.chunk_index) for item in first] == [
        ("a.md", 0),
        ("b.md", 0),
        ("b.md", 1),
    ]
    assert [item.chunk.chunk_id for item in first] == [item.chunk.chunk_id for item in second]


def test_local_manual_source_is_preferred_when_scores_tie() -> None:
    index = build_keyword_index(
        sources=(
            _source("web", "web", "https://example.test/camera"),
            _source("manual", "local_file", "manual.md", manual=True),
        ),
        chunks=(
            _chunk("web", 0, "camera mount"),
            _chunk("manual", 0, "camera mount"),
        ),
    )

    results = index.query("camera")

    assert [item.source.source_id for item in results] == ["manual", "web"]
    assert results[0].source.manufacturer_or_manual is True


def test_empty_keyword_query_returns_no_results() -> None:
    index = build_keyword_index(
        sources=(_source("notes", "local_file", "notes.txt"),),
        chunks=(_chunk("notes", 0, "camera mount"),),
    )

    assert index.query(" ?! ") == ()


def _source(
    source_id: str,
    source_type: str,
    uri: str,
    *,
    manual: bool = False,
) -> SourceMetadata:
    return SourceMetadata(
        source_id=source_id,
        type=source_type,
        title=uri,
        uri=uri,
        manufacturer_or_manual=manual,
    )


def _chunk(
    source_id: str,
    chunk_index: int,
    text: str,
    *,
    section: str | None = None,
) -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=f"{source_id}_{chunk_index}",
        source_id=source_id,
        text=text,
        chunk_index=chunk_index,
        section=section,
    )
