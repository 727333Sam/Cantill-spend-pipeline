# Decisions

## Spend and exclusions

- Company A ERP values are already net; tool values are gross.
- A VAT is parsed as decimal or percentage; blank VAT defaults to 15%.
- Only A `Paid` and `Approved` tool statuses are included. `Cancelled` wins first, then `Rejected`, `On Hold`, `Submitted`, and `Disputed` map to `NOT_APPROVED`.
- Repeated A tool exports are `DUPLICATE`.
- For an unmatched repeated A tool-export key, the first occurrence is retained and later occurrences are `DUPLICATE`; if an occurrence also matches ERP, the ERP record wins.
- A tool records with a normalized PO/PO-item match and net amount within 8% of an ERP line are `DUPLICATE`; the ERP line remains included.
- B uses explicit `currency_rate` first, then the invoice-month `units_per_usd` rate for non-USD currency. USD remains unchanged. If the exact invoice month is absent, the nearest valid month for the same currency is used; ties choose the earlier month. If no valid same-currency rate exists for an included row, the run fails explicitly instead of emitting zero spend.
- The supplied CAD rows B005026-B005030 have invoice months 2022-05, 2022-06, and 2022-07, absent from the FX table. Their deterministic nearest-CAD fallback is 1.35 units of CAD per USD, from 2022-12; their negative amounts remain negative USD credits.
- B seed rows with `include=0` are authoritative exact-row `NON_PROCUREMENT` decisions; conservative account/description rules cover additional clearly non-procurement rows.

## Non-procurement

B and C text/account rules exclude clearly intercompany, tax/sales-tax, revenue, royalty, partner, financing/interest, and related entries. IC account descriptions are treated conservatively as intercompany rather than inferred third-party spend.

## Ambiguity

- Impossible and blank dates remain in the audit as parse errors; they do not silently become a default date.
- For the generic future-company path, missing/invalid FX remains an audit error and does not silently become a known converted amount; Company B now uses the documented nearest-month fallback and fails explicitly when no same-currency rate exists.
- Excluded rows have blank category levels, matching the output template convention.
- Blank/generic descriptions receive low classifier confidence.
- No category name is embedded in code; all category paths come from the runtime taxonomy.
- Negative included amounts are retained as credits/reversals rather than silently dropped; the brief does not instruct the pipeline to discard them.
