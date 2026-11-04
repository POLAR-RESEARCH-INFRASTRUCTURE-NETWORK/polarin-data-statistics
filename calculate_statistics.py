
import json
import time
from collections import Counter
from datetime import datetime, timezone

import requests

BASE = "https://geonetwork.s4polarin.eu/polarin-catalogue-api"
PAGE_SIZE = 200

session = requests.Session()
session.headers.update({"Accept": "application/json"})


def nonempty(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def fetch_records():
    records = []
    start = 0
    expected = None

    while True:
        response = session.get(
            f"{BASE}/records",
            params={
                "start_position": start,
                "number_of_records": PAGE_SIZE
            },
            timeout=90
        )
        response.raise_for_status()
        payload = response.json()

        batch = payload.get("results")
        if not isinstance(batch, list):
            raise ValueError("Invalid API response: missing results")

        total = payload.get("total_records")
        if not isinstance(total, int) or total < 0:
            raise ValueError("Invalid API response: total_records")

        if expected is None:
            expected = total
        elif total != expected:
            raise ValueError("Catalogue changed during download")

        if not batch:
            break

        records.extend(batch)
        start += len(batch)

        print(f"Downloaded {len(records)} / {expected}")

        if len(records) >= expected:
            break

        if len(batch) < PAGE_SIZE:
            raise ValueError("Incomplete API page")

        time.sleep(0.1)

    if len(records) != expected:
        raise ValueError("Incomplete catalogue download")

    uuids = [r.get("uuid") for r in records]

    if any(not nonempty(uuid) for uuid in uuids):
        raise ValueError("Records with missing UUID")

    if len(set(uuids)) != len(records):
        raise ValueError("Duplicate UUIDs detected")

    return records, expected


def count_values(records, field):
    counts = Counter()

    for record in records:
        value = record.get(field)

        if isinstance(value, list):
            counts.update(
                set(str(item) for item in value if nonempty(item))
            )
        elif nonempty(value):
            counts[str(value)] += 1

    return dict(counts.most_common())


def calculate_statistics(records, total):
    uuids = {r["uuid"] for r in records}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": f"{BASE}/records",
        "records_downloaded": len(records),
        "total_records_reported": total,
        "unique_uuids": len(uuids),

        "records_with_data_available": sum(
            r.get("isDataAvailable") is True for r in records
        ),
        "records_displayable": sum(
            r.get("displayableDataset") is True for r in records
        ),
        "distinct_ri_values": len({
            r.get("ri") for r in records if nonempty(r.get("ri"))
        }),

        "with_spatial_extent": sum(
            isinstance(r.get("spatialExtent"), dict)
            and all(
                r["spatialExtent"].get(k) is not None
                for k in (
                    "westBoundLongitude",
                    "eastBoundLongitude",
                    "southBoundLatitude",
                    "northBoundLatitude"
                )
            )
            for r in records
        ),

        "with_temporal_coverage": sum(
            nonempty(r.get("timeCoverageStart"))
            and nonempty(r.get("timeCoverageEnd"))
            for r in records
        ),

        "with_doi": sum(
            nonempty(r.get("doi")) or nonempty(r.get("doiUrl"))
            for r in records
        ),

        "by_location": count_values(records, "location"),
        "by_ri": count_values(records, "ri"),
        "by_ri_type": count_values(records, "riType"),
        "by_earth_system": count_values(records, "climateSpheres"),
        "by_related_parameters": count_values(records, "relatedParams"),
        "by_layer_type": count_values(records, "layerType")
    }


def main():
    records, total = fetch_records()
    stats = calculate_statistics(records, total)

    with open("polarin-statistics.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"Statistics generated successfully: {total} records")


if __name__ == "__main__":
    main()
