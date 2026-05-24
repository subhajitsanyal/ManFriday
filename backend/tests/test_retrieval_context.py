from pathlib import Path

from manfriday.retrieval import RetrievalContextBuilder

FIXTURES = Path(__file__).parent / "fixtures" / "retrieval"


def test_retrieval_context_builder_returns_citations_for_relevant_chunks() -> None:
    context = RetrievalContextBuilder(local_docs_dir=FIXTURES).build("hex key")

    assert len(context.chunks) == 1
    assert context.citations[0].citation_id == "cite_1"
    assert context.citations[0].source_uri == "notes.txt"
    assert context.citations[0].source_title == "notes"
    assert context.citations[0].section is None


def test_retrieval_context_builder_prefers_manual_local_result_when_scores_tie() -> None:
    context = RetrievalContextBuilder(local_docs_dir=FIXTURES).build("camera mount")

    assert context.citations[0].source_uri == "workbench_manual.md"
    assert context.citations[0].source_title == "Workbench Safety Manual"
    assert context.citations[0].section == "Clamp Setup"
