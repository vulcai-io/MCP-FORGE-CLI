# Generated examples — real-world codebases

Unlike `simples_examples/` (small synthetic fixtures, one per language),
this folder holds mcp-forge runs against real, unmodified third-party
codebases — to show how the generator behaves on code it wasn't tuned
against.

## Entries

| Folder | Source | Score | Tools |
|---|---|---|---|
| [`carddemo_cobol/`](results/carddemo_cobol/) | [aws-samples/aws-mainframe-modernization-carddemo](https://github.com/aws-samples/aws-mainframe-modernization-carddemo) (`app/cbl`) | 7.2/10 | 6 |
| [`ocgcore_src/`](results/ocgcore_src/) | ocgcore (C/C++ duel engine behind the EDOPro Yu-Gi-Oh! client) — source not published, see folder's README | 7.2/10 | 189 |

See each folder's `README.md` for the source command, the real
`eval_report.json` score, and what that specific example demonstrates.
