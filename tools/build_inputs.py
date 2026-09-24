#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.generators import all_campaign_instances  # noqa: E402
from src.model import dump_instance  # noqa: E402


def main() -> int:
    destination = REPO / "instances" / "campaign"
    destination.mkdir(parents=True, exist_ok=True)
    for old in destination.glob("*.json"):
        old.unlink()
    records = []
    for order, (instance, obligations) in enumerate(all_campaign_instances()):
        filename = f"{order:03d}-{instance.name}.json"
        dump_instance(instance, destination / filename)
        records.append(
            {
                "order": order,
                "name": instance.name,
                "group": instance.group,
                "file": f"campaign/{filename}",
                "nodes": len(instance.nodes),
                "capacity": instance.capacity,
                "recipes": instance.recipe_count,
                "contractive": instance.contractive,
                **obligations,
            }
        )
    index = {
        "schema": 1,
        "case_count": len(records),
        "states": [8, 16, 32, 64],
        "records": records,
    }
    with (REPO / "instances" / "index.json").open("w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2)
        handle.write("\n")
    print(f"wrote {len(records)} cases to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
