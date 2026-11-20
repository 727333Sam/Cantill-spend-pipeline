# Final Engineering Audit

This audit compares the implementation with the four-page Cantill.ai brief and records only checks actually run against the supplied external kit. The kit remains outside the repository.

| Requirement | Status | Evidence | Impact / remaining issue |
|---|---|---|---|
| Config-driven ingestion | PASS | `configs/company_a.json`, `company_b.json`, and `company_c.example.json`; CLI accepts config and external kit paths. | C users must map their actual columns in a copied config. |
| One row per input record and exact output schema | PASS | A output has 65,549 rows (`37,029 + 28,520`); B has 41,028 rows; headers match the 11-column template. | None found. |
| A net spend and gross-to-net VAT | PASS | ERP uses net `value_zar`; tool VAT parses decimal/percent forms and defaults blank VAT to 15%. | Tool records with malformed amounts are auditable but emitted as zero spend. |
| B USD conversion | PASS | Explicit `currency_rate` is used first; exact invoice-month FX is next; nearest valid same-currency month is the deterministic fallback; USD is unchanged. | An included row with no valid same-currency FX anywhere fails explicitly instead of becoming zero spend. |
| Status and exclusion codes | PARTIAL | A `Cancelled` maps to `CANCELLED`; rejected/hold/submitted/disputed map to `NOT_APPROVED`; B has no status column. | The brief does not define B document-type status semantics, so B uses seed decisions plus conservative procurement rules. |
| Count A purchases once across systems | PARTIAL | ERP/tool PO and amount matching is deterministic; repeated unmatched tool exports keep the first copy and mark later copies `DUPLICATE`. | Matching still relies on source PO and amount evidence; unmatched aliases remain a known risk. |
| Supplier de-duplication | PASS | A label supplier keys are preserved; other records use vendor IDs or deterministic normalized-name hashes. | Name-only aliases without strong textual similarity may remain separate. |
| Item de-duplication | PARTIAL | Stable material/item IDs are preferred; descriptions receive deterministic hashes. | Description-only semantic equivalence is conservative and not fully inferred. |
| Runtime taxonomy classification to lowest level | PASS | Taxonomy files are loaded at runtime; included outputs have valid A/B category paths and blank levels below depth. | Model quality is not claimed as an accuracy metric without a separately run evaluation protocol. |
| A label-hidden / C label-free fallback | PASS | Runtime taxonomy nearest-text fallback is exercised by classifier tests and generic C path. | The current committed outputs use supplied A labels and B seeds as configured. |
| Four-level unseen taxonomy support | PASS | Classifier pads taxonomy depth to the exact four output columns; generic config accepts four taxonomy columns. | A real C dataset was not available in the supplied kit, so C remains unverified on real data. |
| Local/free unattended execution | PASS | No API calls or API keys; tests pass and measured full runs were A 573.36 seconds and B 324.32 seconds on this environment. | Runtime depends on hardware; both observed runs are below 60 minutes. |
| Privacy and repository hygiene | PASS | No PDF or raw input CSV exists under the repository; kit and runtime outputs are ignored except required `submission/*.csv`. | `outputs/` contains local audit artifacts but is ignored and not submission data. |

## Verified final outputs

- `submission/727333sam__A.csv`: 65,549 rows, 11 columns, no duplicate record IDs.
- `submission/727333sam__B.csv`: 41,028 rows, 11 columns, no duplicate record IDs.
- All included A/B category triples exist in their runtime taxonomy.
- All confidence values are within `[0, 1]`.
- All supplier and item keys are non-empty.
- All excluded rows have zero spend and blank category levels.
- B's 3,000 supplied seed labels agree exactly with the regenerated B decisions: 450 excluded and 2,550 included.
- 11 automated tests pass.

## Remaining risks

The largest residual scoring risks are semantic rather than mechanical: A cross-system matching can miss records with both missing PO evidence and weak supplier text, and item descriptions without stable codes are only conservatively grouped. B's non-procurement rules beyond the 450 seed exclusions are transparent heuristics and should be reviewed if additional blind-test examples become available.
