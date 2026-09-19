"""Discovery commands intentionally have no client write/install operation."""
import argparse
import json
import sys

from .discovery import discover
from .inventory import inventory
from .io import write_json
from .mpq import extract


def main(argv=None):
    parser = argparse.ArgumentParser(description='Inventory WotLK mounts and discover Retail candidates')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('extract', help='Read three original DBCs from ordered MPQ archives')
    p.add_argument('--stormlib', required=True)
    p.add_argument('--archive', action='append', required=True, help='Highest priority first; repeat')
    p.add_argument('--output', required=True, help='Fresh directory; parent must exist')
    p = sub.add_parser('inventory', help='Resolve mounted auras through explicit server model data')
    p.add_argument('--dbc-dir', required=True)
    p.add_argument('--creature-models', help='CSV from the query in docs/BUILD.md')
    p.add_argument('--output', required=True, help='Fresh JSON file; parent must exist')
    p = sub.add_parser('discover', help='Compare Retail metadata; never approve a replacement')
    for flag in ('inventory', 'retail-dir', 'listfile', 'profile', 'families', 'output'):
        p.add_argument('--' + flag, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'extract':
            result = extract(args.stormlib, args.archive, args.output)
        elif args.command == 'inventory':
            result = inventory(args.dbc_dir, args.creature_models)
            write_json(args.output, result)
        else:
            result = discover(args.inventory, args.retail_dir, args.listfile, args.profile, args.families)
            write_json(args.output, result)
        print(json.dumps(result.get('summary', result), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f'wxl-mounts: {error}', file=sys.stderr)
        return 2
