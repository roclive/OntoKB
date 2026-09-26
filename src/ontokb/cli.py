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
import json
import logging
import shutil
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
    p_migrate = sub.add_parser("migrate-ontology", help="preview or apply the Schema.org profile migration")
    p_migrate.add_argument("--apply", action="store_true", help="back up, migrate, and regenerate vault projections")
    p_migrate.add_argument("--report", default="data/ontology-migration-report.json")
    p_migrate.add_argument("--overrides", default="ontology/migration-v2.yaml")
    p_export = sub.add_parser("export-jsonld")
    p_export.add_argument("--out", default="data/knowledge-graph.jsonld")
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

    if args.cmd == "migrate-ontology":
        from .migration import load_overrides, migrate_graph, export_jsonld
        from datetime import datetime, timezone
        backup_dir = ROOT / "data/backups"
        vault_backup = None
        if args.apply:
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            vault_backup = shutil.make_archive(str(backup_dir / f"vault-before-schema-v2-{stamp}"),
                                               "zip", pipe.vault.root)
        result = migrate_graph(pipe.graph, pipe.ontology, backup_dir,
                               load_overrides(_resolve(args.overrides)), apply=args.apply)
        if vault_backup:
            result["vault_backup"] = vault_backup
        report = _resolve(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if result["applied"]:
            for row in pipe.graph.conn.execute("SELECT name FROM entities"):
                pipe.vault.write_entity_note(pipe.graph, row["name"])
            for note in (pipe.vault.root / "Sources").glob("*.md"):
                lines = note.read_text(encoding="utf-8").splitlines(keepends=True)
                for i, line in enumerate(lines):
                    if line.startswith("- [["):
                        for old, new in pipe.ontology.relation_aliases.items():
                            line = line.replace(f"**{old}**", f"**{new}**")
                        lines[i] = line
                note.write_text("".join(lines), encoding="utf-8")
            pipe.export_graph_html()
            export_jsonld(pipe.graph, pipe.ontology, ROOT / "data/knowledge-graph.jsonld")
        print(json.dumps({k: v for k, v in result.items() if k not in {"entities", "relations"}}, ensure_ascii=False, indent=2))
        print(f"report: {report}")
        if result["errors"]:
            return 1
    elif args.cmd == "export-jsonld":
        from .migration import export_jsonld
        print(export_jsonld(pipe.graph, pipe.ontology, _resolve(args.out)))
    elif args.cmd == "status":
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
