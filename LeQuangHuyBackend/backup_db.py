"""Create a consistent SQLite snapshot for VPS transfer."""

import argparse
import os
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    source = Path(os.getenv('ATTENDANCE_DB', Path(__file__).with_name('attendance.db')))
    if not source.is_file():
        parser.error(f'Database does not exist: {source}')
    if args.destination.resolve() == source.resolve():
        parser.error('Destination must differ from source database')
    if args.destination.exists():
        parser.error(f'Destination already exists: {args.destination}')
    with sqlite3.connect(source) as original, sqlite3.connect(args.destination) as snapshot:
        original.backup(snapshot)
        if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            parser.error('Snapshot integrity check failed')
    print(f'Snapshot created: {args.destination}')


if __name__ == '__main__':
    main()
