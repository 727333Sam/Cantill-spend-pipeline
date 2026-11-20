# Approach

## Pipeline design

The runner loads company mappings, source files, taxonomies, optional labels/seeds, and FX tables through JSON config. It normalizes dates and amounts, applies gross-to-net and currency rules, assigns spend/exclusion decisions, creates stable supplier and item keys, and writes the strict public schema. Raw values and parser/FX/matching decisions remain in an optional internal JSONL audit.

## Matching

Company A uses normalized PO numbers and PO line numbers, with a net-value tolerance, to match invoice-tool records to ERP goods receipts. ERP wins when the match is strong. Repeated tool exports are collapsed by normalized invoice number, net amount, and description. Without a strong cross-system match, the tool record remains an independent included purchase candidate.

## Deduplication

A ERP labels supply the golden supplier/item keys directly. Tool records matched to ERP inherit those keys; unmatched A names and all descriptions are normalized deterministically. B supplier keys use stable vendor IDs. B item keys prefer material numbers and otherwise normalized descriptions.

## Classification

A and B taxonomies are loaded at runtime. B seed labels train a local TF-IDF word/character classifier. A labels train only against ERP text and category labels, and a label-free fallback uses the runtime taxonomy itself. The Company C path has no labels and uses the same local taxonomy fallback. No paid API or API key is used.

## Validation

The test suite covers amount/date parsing, VAT, statuses, duplicate precedence, exact output columns, runtime taxonomy depth, supplier/item keys, B seed exclusions, and synthetic end-to-end behavior. The final run produced 65,549 A rows and 41,028 B rows with exact template columns, unique record IDs, non-empty keys, valid taxonomy paths, and confidence in `[0, 1]`. All 3,000 supplied B seed decisions agree with the regenerated B output (450 excluded and 2,550 included). No classification accuracy score is claimed because a separate leakage-safe held-out evaluation was not run.

## Runtime and cost

Measured full runs on the development environment were 573.36 seconds for A and 324.32 seconds for B, both below the 60-minute requirement. API cost per 1,000 lines: `$0`; no external AI service is called.

## Known limitations

Cross-system A matching is strongest when PO and amount evidence are present. Description-only item equivalence and unseen-company semantic classification are conservative, and a real Company C dataset was not included in the supplied kit, so C is validated synthetically/configurationally rather than on blind-test data.
