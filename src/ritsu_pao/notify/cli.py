"""Slack通知CLI — publish結果 + note原稿配布"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ritsu_pao.schemas import MetaJson, ScriptXJson
from ritsu_pao.notify.slack import notify_note_distribution, notify_publish_result

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="因果律 Slack通知")
    parser.add_argument(
        "--publish-dir",
        type=Path,
        default=Path("/srv/inga/output/publish/latest"),
        help="Publish output directory",
    )
    args = parser.parse_args()

    pub_dir: Path = args.publish_dir

    # meta.json読込
    meta_path = pub_dir / "meta.json"
    if not meta_path.exists():
        logger.error("meta.json not found in %s", pub_dir)
        sys.exit(1)
    meta = MetaJson.model_validate_json(meta_path.read_text(encoding="utf-8"))

    # publish結果通知
    script_x: ScriptXJson | None = None
    sx_path = pub_dir / "script_x.json"
    if sx_path.exists():
        script_x = ScriptXJson.model_validate_json(sx_path.read_text(encoding="utf-8"))

    files: dict[str, Path] = {}
    for f in pub_dir.iterdir():
        if f.is_file():
            files[f.name] = f

    notify_publish_result(meta, script_x, files)

    # note原稿配布
    note_path = pub_dir / "note.md"
    if note_path.exists():
        note_md = note_path.read_text(encoding="utf-8")
        notify_note_distribution(note_md, meta)

    logger.info("All notifications sent")


if __name__ == "__main__":
    main()
