#!/usr/bin/env python3
"""Move legacy staff photos from the public upload folder to the private one, reversibly.

Before photos became private, field-work photos, completion evidence and correction photos were saved
in the public upload folder. The application already refuses to serve those files at ``/uploads`` and
serves them to staff from wherever they are. This tool finishes the job in small, checkable steps:

  report      read-only: classify every file a staff record refers to
  copy        copy public-only files into the private folder, verifying a SHA-256 hash (never overwrites)
  verify      check that every file is in the private folder and matches its public copy
  quarantine  move the now-redundant public copies into a quarantine folder (not deleted)
  restore     move quarantined files back to the public folder (the rollback for ``quarantine``)

``copy``, ``quarantine`` and ``restore`` do nothing unless ``--apply`` is given. The database is only
ever opened read-only. Nothing is deleted: after ``quarantine`` the originals are in the quarantine
folder, and deleting that folder is a separate, manual decision.

Example (dry run, then apply):
  python scripts/private_photo_migration.py report --db instance/civicpulse.db --public uploads --private private_uploads
  python scripts/private_photo_migration.py copy --db ... --public ... --private ... --apply
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys

REFERENCES = (
    ("issue_work_updates", "field-work photo"),
    ("resolution_reviews", "completion evidence"),
    ("resolution_follow_up_events", "correction photo"),
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(name):
    return bool(name) and name == os.path.basename(name) and not name.startswith(".") \
        and os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS


def read_references(db_path):
    """(table, row id, file name) for every staff record with a photo, plus the names used by complaints."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows = []
        for table, _label in REFERENCES:
            if table in existing:
                rows += [(table, rid, name) for rid, name in conn.execute(
                    f"SELECT id, image_filename FROM {table} WHERE image_filename IS NOT NULL AND image_filename <> ''")]
        complaint_names = set()
        if "complaints" in existing:
            complaint_names = {r[0] for r in conn.execute("SELECT image_filename FROM complaints WHERE image_filename IS NOT NULL")}
        return rows, complaint_names
    finally:
        conn.close()


def classify(db_path, public, private):
    rows, complaint_names = read_references(db_path)
    items = []
    for table, rid, name in rows:
        item = {"table": table, "id": rid, "file": name, "status": None, "sha256": None}
        pub, priv = os.path.join(public, name), os.path.join(private, name)
        if not safe_name(name):
            item["status"] = "unsafe-name"
        elif name in complaint_names:
            item["status"] = "shared-with-complaint-photo"  # must stay public; never move
        else:
            in_pub, in_priv = os.path.isfile(pub), os.path.isfile(priv)
            if in_pub and in_priv:
                a, b = sha256(pub), sha256(priv)
                item["status"], item["sha256"] = ("both-identical", a) if a == b else ("both-different", None)
            elif in_priv:
                item["status"], item["sha256"] = "private-only", sha256(priv)
            elif in_pub:
                item["status"], item["sha256"] = "public-only", sha256(pub)
            else:
                item["status"] = "missing"
        items.append(item)
    return items


def summarize(items):
    counts = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


def write_manifest(path, items, args):
    if not path:
        return
    with open(path, "w") as handle:
        json.dump({"db": args.db, "public": args.public, "private": args.private, "items": items}, handle, indent=1)


def cmd_report(args):
    items = classify(args.db, args.public, args.private)
    counts = summarize(items)
    for item in items:
        print(f"{item['status']:28} {item['table']}#{item['id']}  {item['file']}")
    print("\nsummary:", json.dumps(counts, sort_keys=True) or "{}", f"({len(items)} references)")
    write_manifest(args.manifest, items, args)
    blocking = counts.get("both-different", 0) + counts.get("unsafe-name", 0) + counts.get("shared-with-complaint-photo", 0)
    if blocking:
        print("ATTENTION: files that cannot be mapped safely were found; nothing will be moved for them.")
        return 2
    return 0


def cmd_copy(args):
    items = classify(args.db, args.public, args.private)
    todo = [i for i in items if i["status"] == "public-only"]
    print(f"{len(todo)} public-only file(s) to copy" + ("" if args.apply else " (dry run; add --apply)"))
    copied = 0
    if args.apply:
        os.makedirs(args.private, exist_ok=True)
    for item in todo:
        src, dst = os.path.join(args.public, item["file"]), os.path.join(args.private, item["file"])
        print(f"  copy {item['file']}")
        if not args.apply:
            continue
        if os.path.exists(dst):  # appeared since classification: never overwrite
            print("    skipped: destination already exists")
            continue
        temp = dst + ".part"
        shutil.copy2(src, temp)
        if sha256(temp) != item["sha256"]:
            os.remove(temp)
            print("    FAILED: hash mismatch, nothing kept")
            return 1
        os.replace(temp, dst)
        copied += 1
    if args.apply:
        print(f"copied {copied}")
    write_manifest(args.manifest, classify(args.db, args.public, args.private), args)
    return 0


def cmd_verify(args):
    items = classify(args.db, args.public, args.private)
    counts = summarize(items)
    bad = [i for i in items if i["status"] in ("public-only", "both-different", "unsafe-name", "shared-with-complaint-photo")]
    missing = [i for i in items if i["status"] == "missing"]
    for item in bad + missing:
        print(f"{item['status']:28} {item['table']}#{item['id']}  {item['file']}")
    print("summary:", json.dumps(counts, sort_keys=True))
    if bad or (args.strict and missing):
        print("VERIFY FAILED")
        return 1
    if missing:
        print("note: referenced files that exist nowhere are listed above; they were already missing before the migration")
    print("VERIFY OK: every present file is in the private folder")
    return 0


def cmd_quarantine(args):
    items = classify(args.db, args.public, args.private)
    if any(i["status"] in ("public-only", "both-different", "unsafe-name", "shared-with-complaint-photo") for i in items):
        print("Refusing to quarantine: run report/copy/verify first; some files are not safely mapped.")
        return 1
    todo = [i for i in items if i["status"] == "both-identical"]
    print(f"{len(todo)} public copy(ies) to quarantine into {args.quarantine}" + ("" if args.apply else " (dry run; add --apply)"))
    if args.apply:
        os.makedirs(args.quarantine, exist_ok=True)
    for item in todo:
        print(f"  move {item['file']}")
        if args.apply:
            dst = os.path.join(args.quarantine, item["file"])
            if os.path.exists(dst):
                print("    skipped: already in quarantine")
                continue
            shutil.move(os.path.join(args.public, item["file"]), dst)
    return 0


def cmd_restore(args):
    if not os.path.isdir(args.quarantine):
        print("nothing to restore")
        return 0
    names = sorted(os.listdir(args.quarantine))
    print(f"{len(names)} file(s) to restore into {args.public}" + ("" if args.apply else " (dry run; add --apply)"))
    for name in names:
        dst = os.path.join(args.public, name)
        print(f"  restore {name}" + ("  (skipped: already exists)" if os.path.exists(dst) else ""))
        if args.apply and not os.path.exists(dst):
            shutil.move(os.path.join(args.quarantine, name), dst)
    return 0


COMMANDS = {"report": cmd_report, "copy": cmd_copy, "verify": cmd_verify, "quarantine": cmd_quarantine, "restore": cmd_restore}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--db", required=True, help="SQLite database file (opened read-only)")
    parser.add_argument("--public", required=True, help="public upload folder (UPLOAD_FOLDER)")
    parser.add_argument("--private", required=True, help="private upload folder (PRIVATE_UPLOAD_FOLDER)")
    parser.add_argument("--quarantine", help="where quarantine moves public copies (default: <public>/../uploads_quarantine)")
    parser.add_argument("--manifest", help="write a JSON manifest of every reference and its status")
    parser.add_argument("--apply", action="store_true", help="actually change files (otherwise a dry run)")
    parser.add_argument("--strict", action="store_true", help="verify: also fail if referenced files are missing")
    args = parser.parse_args(argv)
    args.quarantine = args.quarantine or os.path.join(os.path.dirname(os.path.abspath(args.public)), "uploads_quarantine")
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
