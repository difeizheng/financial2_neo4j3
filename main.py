#!/usr/bin/env python3
"""CLI entry point: parse Excel → JSON → (optionally) Neo4j."""
import argparse
import os
import sys

from config import OUTPUT_DIR
from parser.excel_reader import parse_workbook
from export.json_exporter import export_json


def main():
    ap = argparse.ArgumentParser(
        description="Parse financial model Excel to knowledge graph JSON (and optionally import to Neo4j)."
    )
    ap.add_argument("excel", help="Path to the Excel file")
    ap.add_argument("--sheets", nargs="*", help="Sheet names to parse (default: all)")
    ap.add_argument("--output", default=OUTPUT_DIR, help="Output directory for JSON files")
    ap.add_argument("--llm", action="store_true",
                    help="Use LLM for intelligent section detection (requires API key in .env)")
    ap.add_argument("--neo4j", action="store_true", help="Import into Neo4j after parsing")
    args = ap.parse_args()

    if not os.path.exists(args.excel):
        print(f"Error: file not found: {args.excel}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing: {os.path.basename(args.excel)}")
    print(f"Sheets : {args.sheets or 'all'}")

    llm_provider = None
    if args.llm:
        from llm import get_provider
        llm_provider = get_provider()
        print(f"LLM    : {llm_provider.name()}")

    workbook = parse_workbook(args.excel, sheet_names=args.sheets, llm_provider=llm_provider)

    total_cells = sum(len(getattr(s, "_cells") or []) for s in workbook.sheets)
    total_deps = sum(
        len(c.formula_refs or [])
        for s in workbook.sheets
        for c in (getattr(s, "_cells") or [])
    )
    total_formulas = sum(
        1 for s in workbook.sheets
        for c in (getattr(s, "_cells") or [])
        if c.formula_raw
    )

    nodes_path, edges_path = export_json(workbook, args.output)

    print(f"\nParse results:")
    print(f"  Sheets parsed : {len(workbook.sheets)}")
    print(f"  Cells         : {total_cells}")
    print(f"  Formula cells : {total_formulas}")
    print(f"  Dependencies  : {total_deps}")
    print(f"\nJSON output:")
    print(f"  {nodes_path}")
    print(f"  {edges_path}")

    if args.neo4j:
        from graph.neo4j_client import Neo4jClient
        from graph.importer import import_from_json

        print("\nImporting to Neo4j...")
        client = Neo4jClient()
        if not client.verify_connectivity():
            print("Error: cannot connect to Neo4j. Check NEO4J_URI/USER/PASSWORD in .env", file=sys.stderr)
            sys.exit(1)

        counts = import_from_json(nodes_path, edges_path, client)
        client.close()

        print("Neo4j import complete:")
        for k, v in counts.items():
            print(f"  {k:<15}: {v}")


if __name__ == "__main__":
    main()
