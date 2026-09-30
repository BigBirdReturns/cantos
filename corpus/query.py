"""Read-only access to the bulk corpus SQLite index."""
from pathlib import Path
import argparse
import json
import sqlite3


def select_rows(db_path, *, kind=None, hardware=None, model=None, engine=None,
                scenario=None, unit=None, limit=25, offset=0):
    """Return the established query result shape from a read-only corpus."""
    if not 1 <= limit <= 10000:
        raise ValueError("limit must be 1..10000")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    where = []
    params = []
    for value, field in (
        (kind, "kind"),
        (model, "model"),
        (engine, "engine"),
        (scenario, "json_extract(json,'$.scope.Scenario')"),
        (unit, "json_extract(json,'$.measurement.unit')"),
    ):
        if value is not None:
            where.append(field + " = ?")
            params.append(value)
    if hardware:
        where.append("instr(lower(hardware),lower(?)) > 0")
        params.append(hardware)

    db_path = Path(db_path).resolve()
    db = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    try:
        clause = " WHERE " + " AND ".join(where) if where else ""
        count = db.execute("SELECT count(*) FROM rows" + clause, params).fetchone()[0]
        rows = [
            json.loads(record[0])
            for record in db.execute(
                "SELECT json FROM rows" + clause + " ORDER BY origin,row_id LIMIT ? OFFSET ?",
                params + [limit, offset],
            )
        ]
    finally:
        db.close()
    return {
        "matching_rows": count,
        "returned_rows": len(rows),
        "selection": {
            "kind": kind,
            "hardware": hardware,
            "model": model,
            "engine": engine,
            "scenario": scenario,
            "unit": unit,
            "offset": offset,
        },
        "rows": rows,
        "scope": (
            "Filtered observations, not a joined performance/price estimate. "
            "Native quality, allocation and scenario fields remain attached."
        ),
    }


def row_by_id(db_path, row_id):
    """Return one exact stored row or raise KeyError without changing the DB."""
    db_path = Path(db_path).resolve()
    db = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    try:
        record = db.execute("SELECT json FROM rows WHERE row_id = ?", (row_id,)).fetchone()
    finally:
        db.close()
    if record is None:
        raise KeyError(row_id)
    return json.loads(record[0])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--kind")
    parser.add_argument("--hardware")
    parser.add_argument("--model")
    parser.add_argument("--engine")
    parser.add_argument("--scenario")
    parser.add_argument("--unit")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 10000:
        parser.error("--limit must be 1..10000")
    if args.offset < 0:
        parser.error("--offset must be nonnegative")
    result = select_rows(
        args.db,
        kind=args.kind,
        hardware=args.hardware,
        model=args.model,
        engine=args.engine,
        scenario=args.scenario,
        unit=args.unit,
        limit=args.limit,
        offset=args.offset,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
