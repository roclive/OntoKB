"""ontokb CLI.

  ontokb queue                    # load watch list / configured URLs into the queue
  ontokb ingest <url>             # fetch + process one URL end to end
  ontokb rules                    # run the rule engine over the graph
  ontokb status                   # counts
"""

from __future__ import annotations

import argparse
import logging
import sys

from .models import ContentItem
from .pipeline import Pipeline


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
    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("url")

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

            items += items_from_takeout_csv(yt["takeout_csv"])
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
