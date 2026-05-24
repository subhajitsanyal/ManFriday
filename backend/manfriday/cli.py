import argparse
import json

from manfriday.config.settings import Settings
from manfriday.retrieval import ingest_retrieval_sources
from manfriday.retrieval.summary import ingestion_summary_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(prog="manfriday")
    subcommands = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subcommands.add_parser("ingest", help="Build local retrieval metadata.")
    ingest_parser.add_argument(
        "--local-docs-dir",
        default=None,
        help="Override RETRIEVAL_LOCAL_DOCS_DIR.",
    )
    ingest_parser.add_argument(
        "--online-sources-path",
        default=None,
        help="Override RETRIEVAL_ONLINE_SOURCES_PATH.",
    )
    args = parser.parse_args()
    if args.command == "ingest":
        settings = Settings()
        root = settings.retrieval_local_docs_dir
        if args.local_docs_dir is not None:
            root = root.__class__(args.local_docs_dir)
        online_sources_path = settings.retrieval_online_sources_path
        if args.online_sources_path is not None:
            online_sources_path = online_sources_path.__class__(args.online_sources_path)
        summary = ingest_retrieval_sources(
            local_docs_dir=root,
            online_sources_path=online_sources_path,
        )
        print(json.dumps(ingestion_summary_to_dict(summary), indent=2))


if __name__ == "__main__":
    main()
