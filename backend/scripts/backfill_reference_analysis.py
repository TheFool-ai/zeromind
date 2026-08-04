#!/usr/bin/env python3
"""Queue historical content references for the canonical analysis workflow."""

import argparse
import asyncio
import json
import time

from zeromind.ingestion.analysis_queue import SqlAlchemyReferenceAnalysisQueue
from zeromind.ingestion.backfill import backfill_reference_analysis
from zeromind.ingestion.repository import SqlAlchemyReferenceRepository
from zeromind.shared.database import create_database
from zeromind.workflows.constants import MAIN_ANALYSIS_WORKFLOW_NAME
from zeromind.workflows.repository import SqlAlchemyWorkflowRepository


async def _run(args: argparse.Namespace) -> dict[str, object]:
    database = create_database()
    started = time.monotonic()
    try:
        definitions = [
            item
            for item in await SqlAlchemyWorkflowRepository(
                database.sessions
            ).list_definitions()
            if item.name == MAIN_ANALYSIS_WORKFLOW_NAME and item.status == "active"
        ]
        if len(definitions) != 1:
            raise ValueError(
                "expected exactly one active information analysis workflow"
            )
        result = await backfill_reference_analysis(
            SqlAlchemyReferenceAnalysisQueue(database.sessions),
            SqlAlchemyReferenceRepository(database.sessions),
            all_references=args.all,
            batch_size=args.batch_size,
            limit=args.limit,
            generation=args.generation,
            dry_run=args.dry_run,
            workflow_version=definitions[0].version,
        )
        return {
            "scanned": result.scanned,
            "enqueued": result.enqueued,
            "skipped": result.skipped,
            "status_counts": result.status_counts,
            "generation": args.generation,
            "dry_run": args.dry_run,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", dest="all")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--generation", default="lifecycle-v1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args)), ensure_ascii=False))


if __name__ == "__main__":
    main()
