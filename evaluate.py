"""Score separately collected baseline and RAG SQL against a fixed schema.
Input JSONL rows: {"question": "...", "baseline_sql": "...", "rag_sql": "..."}
Do not claim a reduction until measured on a representative held-out set.
"""
import argparse
import json
from pathlib import Path
from app.guardrails import validate, UnsafeSQL

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('results')
    parser.add_argument('--schema', default='schema.json')
    args = parser.parse_args()
    schema = json.loads(Path(args.schema).read_text())
    rows = [json.loads(line) for line in Path(args.results).read_text().splitlines() if line.strip()]
    if not rows:
        parser.error('Provide at least one paired result')
    failures = {'baseline_sql':0,'rag_sql':0}
    for row in rows:
        for key in failures:
            try:
                validate(row[key], schema)
            except UnsafeSQL:
                failures[key] += 1
    base = failures['baseline_sql']
    print(json.dumps({'questions':len(rows), 'validation_failures':failures,
          'relative_failure_reduction':(base-failures['rag_sql'])/base if base else None}, indent=2))
