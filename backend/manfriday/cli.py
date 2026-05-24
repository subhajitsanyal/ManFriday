import argparse
import json

from manfriday.config.settings import Settings
from manfriday.retrieval import ingest_local_documents
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
    args = parser.parse_args()
    if args.command == "ingest":
        settings = Settings()
        root = settings.retrieval_local_docs_dir
        if args.local_docs_dir is not None:
            root = root.__class__(args.local_docs_dir)
        summary = ingest_local_documents(root)
        print(json.dumps(ingestion_summary_to_dict(summary), indent=2))


if __name__ == "__main__":
    main()
