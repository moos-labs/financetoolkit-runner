# financetoolkit-runner

Runs fundamental-ratio analysis (FinanceToolkit + verified manual statements) via GitHub Actions,
following the one-repo-per-tool runner pattern: the commands live in the **COMMANDS** repository
variable, the workflow is triggered manually (`workflow_dispatch`), and results are collected as
the **results** artifact.

## How to run

1. (Optional) Update the `COMMANDS` repository variable (Settings → Secrets and variables →
   Actions → Variables), e.g.:

   ```
   mkdir -p results
   python scripts/ft_ratios.py 2>&1 | tee results/run.log
   ```

2. Trigger the **Run Analysis** workflow manually (Actions tab → Run workflow), or dispatch it
   through the GitHub API.
3. Download the `results` artifact: `ratios.json` (machine-readable ratios + FinanceToolkit
   attempt log + coverage gaps) and `report.md` (readable report).

## Design

- **Generic**: the company under analysis is just an input CSV (`data/<company>_statements.csv`,
  format: `item, unit, <one column per period>, basis_notes`). Point `STATEMENTS_CSV` at another
  file and set another ticker label to analyse a different company/market — nothing in the
  workflow or script is specific to one exchange.
- **Honest data**: the bundled `data/poul_statements.csv` (Cairo Poultry, EGX: POUL) contains only
  figures verified in the 10-Nov-2026 buy-decision research. Where the verified record has no
  figure (or only a conflicting range), the cell is blank and the report's COVERAGE section names
  the ratio that the missing line item blocks. No number is ever estimated or filled in.
- **Traceable**: the script tries FinanceToolkit's manual-statements API and logs the outcome in
  `ratios.json`; headline ratios are computed directly from the CSV so every value can be traced
  to a line item. Whichever path produced the numbers is stated in the report.
