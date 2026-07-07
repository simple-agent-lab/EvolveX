#!/usr/bin/env python3
"""FROZEN — extract a field from an eval result.json / stamp.json.

Usage: parse_score.py <json-file> [key]   (default key: score)
"""
import json
import sys


def main() -> None:
    doc = json.load(open(sys.argv[1]))
    key = sys.argv[2] if len(sys.argv) > 2 else "score"
    value = doc[key]
    print(value if isinstance(value, str) else json.dumps(value))


if __name__ == "__main__":
    main()
