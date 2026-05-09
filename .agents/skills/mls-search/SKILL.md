---
name: mls-search
description: Run MLS comparable-property searches from a subject address. Supports browser mode, which fills the MLS Listings Residential Search form and stops before submitting
---

# MLS Comparable Search

This skill has two backends:

- **Browser mode**: use the MLS Listings website automation to fill the Residential Search form and stop before submitting.

Browser mode is the default mode. 
## Required Context

Read `references/comparison_rules.md` before deriving search criteria.

For browser automation work, read `references/browser_workflow.md`.

## Script Entry Points

- `scripts/search.py`: MLS Listings browser automation. It fills the form and stops before submitting.

Do not print `.env` secrets. If adding dependencies, run `uv add <package>` from `/Users/xiang/projects/mlsauto`.
