# CardDemo (COBOL) example

**Source:** [aws-samples/aws-mainframe-modernization-carddemo](https://github.com/aws-samples/aws-mainframe-modernization-carddemo) (`app/cbl`, real-world mainframe COBOL, MIT-0 license)

**Score:** 7.2/10 (6 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's COBOL support on a real legacy mainframe codebase (not a synthetic fixture): most of CardDemo's COBOL is monolithic, historical-style (shared WORKING-STORAGE state, not isolated subprograms), so only a handful of real external call targets end up exposed as genuinely executable tools — everything else honestly reports that it cannot be run in isolation rather than pretending to work.

---

Exposes public COBOL functions from the cbl library for runtime execution and data transformation. Enables integration of legacy COBOL procedures with modern applications through standardized function calls.

Généré par **mcp-forge**.

## Installation

```bash
pip install -r requirements.txt
```

## Lancement

```bash
python server.py
```

## Test avec MCP Inspector

```bash
mcp dev server.py
```

## Tools disponibles (6)

### `call_cobdatft`

Call the COBDATFT external program to process date/time formatting operations. Use this when date transformation or time-related processing is required.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `codatecn_rec` | `str` | yes | Date/time control record (alphanumeric string, max 100 chars) |
---
### `call_cee3abd`

Call the CEE3ABD external program to handle abort/termination operations with code and timing parameters. Use this when conditional program termination or error handling is needed.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `abcode` | `str` | yes | Abort/error code (numeric string or alphanumeric identifier) |
| `timing` | `str` | yes | Timing indicator or delay value (numeric string in milliseconds or time unit) |
---
### `call_cbstm03b`

Call the CBSTM03B external program to process statement-related data. Use this when handling statement formatting or generation operations.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `ws_m03b_area` | `str` | yes | Working storage area for M03B processing (structured data buffer, may contain multiple fields) |
---
### `call_mvswait`

Call the MVSWAIT external program to introduce a wait or delay period. Use this when synchronization, polling, or scheduled delays are required.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `mvswait_time` | `str` | yes | Wait duration (numeric string in seconds or milliseconds) |
---
### `call_csutldtc`

Call the CSUTLDTC subprogram to convert and format dates according to a specified format. Use this when date transformation or localization is needed.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `date` | `str` | yes | Input date value (10-character alphanumeric string, format determined by date_format parameter) |
| `date_format` | `str` | yes | Target date format specification (10-character alphanumeric string, e.g., 'YYYY-MM-DD') |
---
### `call_ceedays`

Call the CEEDAYS external program to validate and convert dates between different formats or calculate Lillian day numbers. Use this when you need to test date validity, convert date formats, or obtain Lillian calendar calculations.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `ws_date_to_test` | `str` | yes | The date string to validate or convert (format specified by ws_date_format parameter) |
| `ws_date_format` | `str` | yes | The format specification of the input date (e.g., 'YYYYMMDD', 'DD/MM/YYYY') |
| `output_lillian` | `str` | yes | Flag or format specification for Lillian day number output (e.g., 'Y' for yes, or output format code) |
| `feedback_code` | `str` | yes | Variable name or code reference where the operation result or status feedback will be stored |
---
