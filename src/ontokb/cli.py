"""ontokb CLI.

  ontokb queue                    # load watch list / configured URLs into the queue
  ontokb ingest <url>             # fetch + process one URL end to end
  ontokb rules                    # run the rule engine over the graph
  ontokb backfill                 # rebuild the document tier for pre-refactor data
  ontokb status                   # counts
  ontokb visualize                # regenerate the interactive graph HTML in the vault
  ontokb api                      # serve the graph query JSON API
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .models import ContentItem
from .pipeline import ROOT, Pipeline


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def _make_item(url: str) -> ContentItem:
    if "163.com" in url:
        from .sources.netease import item_from_url

        return item_from_url(url)
    if "youtube.com" in url or "youtu.be" in url:
        from .sources.youtube import _vid

        return ContentItem(id=f"yt:{_vid(url)}", kind="video", source="youtube", url=url)
    raise SystemExit(f"unsupported url: {url}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="ontokb")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    sub.add_parser("rules")
    sub.add_parser("queue")
    sub.add_parser("backfill")
    p_api = sub.add_parser("api")
    p_api.add_argument("--host", default="127.0.0.1")
    p_api.add_argument("--port", type=int, default=8765)
    p_api.add_argument("--db", default=None, help="SQLite graph db path (default: paths.db)")
    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("url")
    p_vis = sub.add_parser("visualize")
    p_vis.add_argument("-o", "--out", default=None,
                       help="output HTML path (default: paths.graph_html or <vault>/Knowledge Graph.html)")

    args = parser.parse_args(argv)
    pipe = Pipeline()

    if args.cmd == "status":
        print(pipe.status())
    elif args.cmd == "rules":
        actions = pipe.run_rules()
        for a in actions:
            print(f"[{a.rule}] {a.action} {a.params}")
        print(f"{len(actions)} action(s) fired")
    elif args.cmd == "queue":
        cfg = pipe.config.get("sources", {})
        yt = cfg.get("youtube", {}) or {}
        items: list[ContentItem] = []
        if yt.get("takeout_csv"):
            from .sources.youtube import items_from_takeout_csv

            items += items_from_takeout_csv(_resolve(yt["takeout_csv"]))
        if yt.get("playlist_url"):
            from .sources.youtube import items_from_playlist

            items += items_from_playlist(yt["playlist_url"], yt.get("cookies_file"))
        for url in (cfg.get("netease", {}) or {}).get("urls") or []:
            items.append(_make_item(url))
        for item in items:
            pipe.graph.upsert_content(item.id, item.kind, item.source, item.url, item.title)
        print(f"queued {len(items)} item(s)")
    elif args.cmd == "ingest":
        item = _make_item(args.url)
        stats = pipe.ingest(item)
        print(stats)
    elif args.cmd == "backfill":
        print(pipe.backfill_documents())
    elif args.cmd == "visualize":
        path = pipe.export_graph_html(args.out)
        print(f"wrote {path}")
    elif args.cmd == "api":
        from .api import run_api

        paths = pipe.config.get("paths", {})
        llm = pipe.config.get("llm", {}) or {}
        db_path = _resolve(args.db or paths.get("db", "data/kb.db"))
        print(f"serving graph API on http://{args.host}:{args.port} using {db_path}", flush=True)
        run_api(
            db_path,
            host=args.host,
            port=args.port,
            provider=llm.get("provider"),
            model=llm.get("model"),
            fallback_model=llm.get("fallback_model"),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
