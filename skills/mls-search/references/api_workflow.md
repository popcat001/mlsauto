# API Workflow

Use this workflow when the user asks to avoid browser login, use API, use Repliers, build a webservice, retrieve comparison analysis, or return comparable results as a table.

Rules:

- Read `MLS_API_KEY` from `/Users/xiang/projects/mlsauto/.env`; never print the key.
- Prefer structured API fields over page scraping.
- Convert `references/comparison_rules.md` criteria into Repliers filters as closely as the API supports.
- If Repliers uses a different field name or cannot express a filter exactly, state the exact fallback.
- Return the criteria used and a comparable-results table.

Expected table columns:

- Distance
- Status
- Last Change Date
- M.O.
- MLS #
- Street Address
- Price
- DOM
- Bds
- Bths
- SqFt
- Lot Size
- Postal City
- Class
- Age

Omit UI-only result-grid controls such as row checkboxes, thumbnail icons, map/action icons, and empty action columns.

Optional analysis columns may be added after the MLS-style columns when useful:

- Address
- Price per SqFt

Implementation guidance:

- Use `skills/mls-search/scripts/search_repliers_api.py` for CLI API searches.
- Keep API code separate from browser form filling.
- Do not change `skills/mls-search/scripts/search.py` browser fill-only behavior unless explicitly asked.
- If adding dependencies, use `uv add <package>` from `/Users/xiang/projects/mlsauto`.

CLI examples:

```bash
python3 skills/mls-search/scripts/search_repliers_api.py \
  "990 Rose Ave, Mountain View, CA 94040"
```

```bash
python3 skills/mls-search/scripts/search_repliers_api.py \
  "990 Rose Ave, Mountain View, CA 94040" \
  --json --limit 10
```

The script:

1. Loads `MLS_API_KEY` from `.env`.
2. Searches Repliers for the subject listing by address.
3. Extracts property facts and coordinates from the subject listing.
4. Builds sold-comparable criteria from `references/comparison_rules.md`.
5. Calls Repliers `/listings` with `status=U`, `lastStatus=Sld`, sold-date filters, subject property filters, and a 1-mile radius converted to kilometers.
6. Prints criteria and comparable results as Markdown or JSON.
