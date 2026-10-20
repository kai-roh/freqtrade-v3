#!/usr/bin/env python3
"""Create a separate protected Demo database credential file without overwriting it."""

import argparse
import os
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    password = secrets.token_hex(32)
    # Exclusive creation preserves existing database credentials on repeated deployment.
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("POSTGRES_DB=phase1\nPOSTGRES_USER=phase1\n")
        stream.write(f"POSTGRES_PASSWORD={password}\n")
        stream.write(
            f"PHASE1_DATABASE_DSN=postgresql://phase1:{password}@phase1-postgres:5432/phase1\n"
        )
    print("database credential file created; values withheld")


if __name__ == "__main__":
    main()
