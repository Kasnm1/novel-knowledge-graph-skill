#!/usr/bin/env python3
"""Export graph.json for Cytoscape Desktop, Gephi, and yEd."""

from __future__ import annotations

import argparse
import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path


GRAPHML = "http://graphml.graphdrawing.org/xmlns"
ET.register_namespace("", GRAPHML)


def text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def add_data(parent: ET.Element, key: str, value) -> None:
    if value not in (None, "", [], {}):
        ET.SubElement(parent, f"{{{GRAPHML}}}data", {"key": key}).text = text(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    source = args.graph.resolve()
    data = json.loads(source.read_text(encoding="utf-8"))
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    entities = data.get("entities", [])
    entity_ids = {item["id"] for item in entities}
    relations = [r for r in data.get("relations", []) if r.get("source_id") in entity_ids and r.get("target_id") in entity_ids]

    with (out / "nodes.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["id", "label", "type", "first_chapter", "last_chapter", "summary", "aliases", "attributes", "current_state"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in entities:
            writer.writerow({
                "id": item.get("id"), "label": item.get("name"), "type": item.get("type"),
                "first_chapter": item.get("first_chapter"), "last_chapter": item.get("last_chapter"),
                "summary": item.get("summary"), "aliases": text(item.get("aliases", [])),
                "attributes": text(item.get("attributes", {})), "current_state": text(item.get("current_state", {})),
            })

    with (out / "edges.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["id", "source", "target", "label", "valid_from", "valid_to", "status", "strength", "description"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in relations:
            writer.writerow({
                "id": item.get("id"), "source": item.get("source_id"), "target": item.get("target_id"),
                "label": item.get("relation_type"), "valid_from": item.get("valid_from"), "valid_to": item.get("valid_to"),
                "status": item.get("status"), "strength": item.get("strength"), "description": item.get("description"),
            })

    root = ET.Element(f"{{{GRAPHML}}}graphml")
    for key_id, target, name, kind in [
        ("n_label", "node", "label", "string"), ("n_type", "node", "type", "string"),
        ("n_first", "node", "first_chapter", "int"), ("n_last", "node", "last_chapter", "int"),
        ("n_summary", "node", "summary", "string"), ("n_aliases", "node", "aliases", "string"),
        ("e_label", "edge", "label", "string"), ("e_from", "edge", "valid_from", "int"),
        ("e_to", "edge", "valid_to", "int"), ("e_status", "edge", "status", "string"),
        ("e_strength", "edge", "strength", "double"), ("e_description", "edge", "description", "string"),
    ]:
        ET.SubElement(root, f"{{{GRAPHML}}}key", {"id": key_id, "for": target, "attr.name": name, "attr.type": kind})
    xml_graph = ET.SubElement(root, f"{{{GRAPHML}}}graph", {"id": "novel", "edgedefault": "directed"})
    for item in entities:
        node = ET.SubElement(xml_graph, f"{{{GRAPHML}}}node", {"id": item["id"]})
        add_data(node, "n_label", item.get("name")); add_data(node, "n_type", item.get("type"))
        add_data(node, "n_first", item.get("first_chapter")); add_data(node, "n_last", item.get("last_chapter"))
        add_data(node, "n_summary", item.get("summary")); add_data(node, "n_aliases", item.get("aliases"))
    for item in relations:
        edge = ET.SubElement(xml_graph, f"{{{GRAPHML}}}edge", {"id": item["id"], "source": item["source_id"], "target": item["target_id"]})
        add_data(edge, "e_label", item.get("relation_type")); add_data(edge, "e_from", item.get("valid_from"))
        add_data(edge, "e_to", item.get("valid_to")); add_data(edge, "e_status", item.get("status"))
        add_data(edge, "e_strength", item.get("strength")); add_data(edge, "e_description", item.get("description"))
    ET.ElementTree(root).write(out / "novel-graph.graphml", encoding="utf-8", xml_declaration=True)

    cyjs = {
        "data": {"title": data.get("metadata", {}).get("title", source.stem)},
        "elements": {
            "nodes": [{"data": {"id": e["id"], "label": e.get("name"), "type": e.get("type"), "first_chapter": e.get("first_chapter"), "last_chapter": e.get("last_chapter"), "summary": e.get("summary", "")}} for e in entities],
            "edges": [{"data": {"id": r["id"], "source": r["source_id"], "target": r["target_id"], "label": r.get("relation_type"), "valid_from": r.get("valid_from"), "valid_to": r.get("valid_to"), "status": r.get("status")}} for r in relations],
        },
    }
    (out / "cytoscape.json").write_text(json.dumps(cyjs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(out), "nodes": len(entities), "edges": len(relations), "files": ["novel-graph.graphml", "cytoscape.json", "nodes.csv", "edges.csv"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
