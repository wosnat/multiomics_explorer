#!/usr/bin/env python3
"""Read gene annotation JSONs from the KG build cache and generate
tests/fixtures/gene_data.py with curated gene records.

Usage:
    python scripts/build_test_fixtures.py

Expects the KG build cache at:
    ../multiomics_biocypher_kg/cache/data/{Organism}/genomes/{Genome}/gene_annotations_merged.json
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from pprint import pformat

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
KG_CACHE = PROJECT_ROOT.parent / "multiomics_biocypher_kg" / "cache" / "data"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
OUTPUT_FILE = FIXTURES_DIR / "gene_data.py"

ANNOTATION_FILES: dict[str, Path] = {}

for organism_dir in sorted(KG_CACHE.iterdir()):
    if not organism_dir.is_dir():
        continue
    genomes_dir = organism_dir / "genomes"
    if not genomes_dir.exists():
        continue
    for genome_dir in sorted(genomes_dir.iterdir()):
        if not genome_dir.is_dir():
            continue
        ann_file = genome_dir / "gene_annotations_merged.json"
        if ann_file.exists():
            key = f"{organism_dir.name}/{genome_dir.name}"
            ANNOTATION_FILES[key] = ann_file

# ---------------------------------------------------------------------------
# Load all annotation data
# ---------------------------------------------------------------------------


def load_annotations(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


ALL_DATA: dict[str, dict] = {}
for key, path in ANNOTATION_FILES.items():
    ALL_DATA[key] = load_annotations(path)


def get_gene(organism_genome: str, locus_tag: str) -> dict:
    """Get a specific gene by organism/genome key and locus_tag."""
    data = ALL_DATA[organism_genome]
    if locus_tag not in data:
        raise KeyError(
            f"Gene {locus_tag} not found in {organism_genome}. "
            f"Available keys (first 5): {list(data.keys())[:5]}"
        )
    return data[locus_tag]


def find_gene(
    organism_genome: str,
    *,
    has_gene_name: bool | None = None,
    is_hypothetical: bool | None = None,
    has_ec: bool | None = None,
    min_ec_count: int = 0,
    has_partial_ec: bool | None = None,
    min_identifiers: int = 0,
    prefer_minimal: bool = False,
    prefer_rich: bool = False,
) -> dict:
    """Find a gene matching criteria in the given organism/genome."""
    data = ALL_DATA[organism_genome]
    candidates = []

    for lt, g in data.items():
        gene_name = g.get("gene_name")
        gene_name_real = gene_name and gene_name != lt
        product = g.get("product", "")
        ec = g.get("ec_numbers", [])

        if has_gene_name is True and not gene_name_real:
            continue
        if has_gene_name is False and gene_name_real:
            continue
        if is_hypothetical is True and "hypothetical" not in product.lower():
            continue
        if is_hypothetical is False and "hypothetical" in product.lower():
            continue
        if has_ec is True and not ec:
            continue
        if has_ec is False and ec:
            continue
        if min_ec_count > 0 and len(ec) < min_ec_count:
            continue
        if has_partial_ec is True:
            if not any("-" in e for e in ec):
                continue
        if min_identifiers > 0:
            if len(g.get("all_identifiers", [])) < min_identifiers:
                continue

        candidates.append(g)

    if not candidates:
        raise ValueError(f"No gene matching criteria in {organism_genome}")

    if prefer_minimal:
        candidates.sort(key=lambda g: len(g))
    elif prefer_rich:
        candidates.sort(key=lambda g: -len(g))

    return candidates[0]


# ---------------------------------------------------------------------------
# Gene selection
# ---------------------------------------------------------------------------

SELECTED_GENES: list[dict] = []

# Prochlorococcus MED4
SELECTED_GENES.append(get_gene("Prochlorococcus/MED4", "PMM0001"))  # dnaN, well-annotated
SELECTED_GENES.append(get_gene("Prochlorococcus/MED4", "PMM0002"))  # hypothetical with gene_name
SELECTED_GENES.append(get_gene("Prochlorococcus/MED4", "PMM0446"))  # coxB, EC numbers, 6 identifiers

# Prochlorococcus MIT9312
SELECTED_GENES.append(get_gene("Prochlorococcus/MIT9312", "PMT9312_0001"))  # dnaN ortholog
SELECTED_GENES.append(get_gene("Prochlorococcus/MIT9312", "PMT9312_0342"))  # minimal hypothetical

# Prochlorococcus NATL2A — well-annotated with gene_name + EC
SELECTED_GENES.append(find_gene(
    "Prochlorococcus/NATL2A",
    has_gene_name=True,
    has_ec=True,
    prefer_rich=True,
))

# Alteromonas MIT1002
SELECTED_GENES.append(get_gene("Alteromonas/MIT1002", "ALT831_RS00180"))  # gene_name = locus_tag fallback
SELECTED_GENES.append(find_gene(
    "Alteromonas/MIT1002",
    is_hypothetical=True,
    prefer_minimal=True,
))  # minimal hypothetical
SELECTED_GENES.append(find_gene(
    "Alteromonas/MIT1002",
    min_ec_count=2,
))  # multiple EC numbers

# Alteromonas EZ55
SELECTED_GENES.append(find_gene(
    "Alteromonas/EZ55",
    has_gene_name=True,
    is_hypothetical=False,
))

# Synechococcus WH8102
SELECTED_GENES.append(get_gene("Synechococcus/WH8102", "SYNW0305"))  # ftsH, many synonyms
SELECTED_GENES.append(find_gene(
    "Synechococcus/WH8102",
    has_gene_name=False,
    is_hypothetical=False,
))  # without gene_name

# Synechococcus CC9311
SELECTED_GENES.append(find_gene(
    "Synechococcus/CC9311",
    has_gene_name=True,
    has_ec=True,
))

# Special cases: gene with many identifiers (6+)
# PMM0446 already has 6 identifiers, but let's find another if possible
for org_key, data in ALL_DATA.items():
    for lt, g in data.items():
        ids = g.get("all_identifiers", [])
        if len(ids) >= 7 and g["locus_tag"] not in {sg["locus_tag"] for sg in SELECTED_GENES}:
            SELECTED_GENES.append(g)
            break
    else:
        continue
    break

# Gene with partial EC number (like 3.4.24.-)
# SYNW0305 already has 3.4.24.-, but let's find another if possible
for org_key, data in ALL_DATA.items():
    for lt, g in data.items():
        ec = g.get("ec_numbers", [])
        if any("-" in e for e in ec) and g["locus_tag"] not in {sg["locus_tag"] for sg in SELECTED_GENES}:
            SELECTED_GENES.append(g)
            break
    else:
        continue
    break

# ---------------------------------------------------------------------------
# Deduplicate (in case any gene was selected twice)
# ---------------------------------------------------------------------------
seen = set()
deduped = []
for g in SELECTED_GENES:
    lt = g["locus_tag"]
    if lt not in seen:
        seen.add(lt)
        deduped.append(g)
SELECTED_GENES = deduped

# ---------------------------------------------------------------------------
# Generate output
# ---------------------------------------------------------------------------


def format_gene_dict(gene: dict, indent: int = 4) -> str:
    """Format a gene dict as a Python literal string."""
    # Use json.dumps for reliable formatting, then convert to Python syntax
    lines = json.dumps(gene, indent=indent, sort_keys=True, default=str)
    # Convert JSON booleans/nulls to Python equivalents
    lines = lines.replace(": true", ": True")
    lines = lines.replace(": false", ": False")
    lines = lines.replace(": null", ": None")
    return lines


def generate_output() -> str:
    parts = []
    parts.append('"""Curated gene fixtures from KG build cache for correctness testing.')
    parts.append("")
    parts.append("Generated by scripts/build_test_fixtures.py — do not edit manually.")
    parts.append("Source: multiomics_biocypher_kg/cache/data/*/genomes/*/gene_annotations_merged.json")
    parts.append('"""')
    parts.append("")
    parts.append("# Full gene records as they appear in annotation JSONs")
    parts.append("GENES = [")

    for gene in SELECTED_GENES:
        formatted = format_gene_dict(gene, indent=4)
        # Indent the whole dict by 4 spaces
        indented = textwrap.indent(formatted, "    ")
        parts.append(indented + ",")

    parts.append("]")
    parts.append("")
    parts.append("")
    parts.append("# Indexes for convenient access")
    parts.append('GENES_BY_LOCUS = {g["locus_tag"]: g for g in GENES}')
    parts.append("")
    parts.append("# Categorized subsets")
    parts.append(
        'GENES_WITH_GENE_NAME = [g for g in GENES if g.get("gene_name") and g["gene_name"] != g["locus_tag"]]'
    )
    parts.append(
        'GENES_WITHOUT_GENE_NAME = [g for g in GENES if not g.get("gene_name") or g["gene_name"] == g["locus_tag"]]'
    )
    parts.append('GENES_WITH_EC = [g for g in GENES if g.get("ec_numbers")]')
    parts.append(
        'GENES_HYPOTHETICAL = [g for g in GENES if "hypothetical" in g.get("product", "").lower()]'
    )
    parts.append("")
    parts.append("")
    parts.append("# Helper: project to resolve_gene return shape")
    parts.append("def as_resolve_gene_result(gene):")
    parts.append("    return {")
    parts.append('        "locus_tag": gene["locus_tag"],')
    parts.append('        "gene_name": gene.get("gene_name"),')
    parts.append('        "product": gene.get("product"),')
    parts.append('        "organism_strain": gene.get("organism_strain"),')
    parts.append("    }")
    parts.append("")
    parts.append("")
    parts.append("# Helper: project to search_genes return shape")
    parts.append("def as_search_genes_result(gene, score=1.0):")
    parts.append("    return {")
    parts.append('        "locus_tag": gene["locus_tag"],')
    parts.append('        "gene_name": gene.get("gene_name"),')
    parts.append('        "product": gene.get("product"),')
    parts.append('        "function_description": gene.get("function_description"),')
    parts.append('        "gene_summary": gene.get("gene_summary"),')
    parts.append('        "organism_strain": gene.get("organism_strain"),')
    parts.append('        "annotation_quality": gene.get("annotation_quality"),')
    parts.append('        "score": score,')
    parts.append("    }")
    parts.append("")
    parts.append("")
    parts.append("# Filter helpers")
    parts.append("def genes_by_organism(organism_substring):")
    parts.append(
        '    return [g for g in GENES if organism_substring in g.get("organism_strain", "")]'
    )
    parts.append("")
    parts.append("")
    parts.append("def genes_with_property(prop):")
    parts.append("    return [g for g in GENES if g.get(prop)]")
    parts.append("")
    parts.append("")
    parts.append("def genes_without_property(prop):")
    parts.append("    return [g for g in GENES if not g.get(prop)]")
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # Write __init__.py if it doesn't exist
    init_file = FIXTURES_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")

    output = generate_output()
    OUTPUT_FILE.write_text(output)

    print(f"Generated {OUTPUT_FILE}")
    print(f"  {len(SELECTED_GENES)} genes selected")
    locus_tags = [g["locus_tag"] for g in SELECTED_GENES]
    for lt in locus_tags:
        g = next(sg for sg in SELECTED_GENES if sg["locus_tag"] == lt)
        org = g.get("organism_strain", "?")
        name = g.get("gene_name", "—")
        product = g.get("product", "—")[:60]
        print(f"    {lt:25s} {org:35s} {name:15s} {product}")
