## EOB PDF extraction evaluation

| Model | Cases | Fields correct | Fully correct cases | Action matches | Mean seconds/case |
|---|---:|---:|---:|---:|---:|
| qwen2.5:3b | 6 | 48/54 | 0/6 | 6/6 | 14.13 |
| qwen2.5:7b | 6 | 50/54 | 3/6 | 5/6 | 20.01 |

| Model | Case | Fields correct | Expected action | Extracted action | Action match | Error |
|---|---|---:|---|---|---|---|
| qwen2.5:3b | CASE-001 | 8/9 | resubmit | resubmit | yes | — |
| qwen2.5:3b | CASE-005 | 8/9 | appeal | appeal | yes | — |
| qwen2.5:3b | CASE-007 | 8/9 | appeal | appeal | yes | — |
| qwen2.5:3b | CASE-010 | 8/9 | appeal | appeal | yes | — |
| qwen2.5:3b | CASE-013 | 8/9 | bill_patient | bill_patient | yes | — |
| qwen2.5:3b | CASE-020 | 8/9 | appeal | appeal | yes | — |
| qwen2.5:7b | CASE-001 | 9/9 | resubmit | resubmit | yes | — |
| qwen2.5:7b | CASE-005 | 9/9 | appeal | appeal | yes | — |
| qwen2.5:7b | CASE-007 | 8/9 | appeal | appeal | yes | — |
| qwen2.5:7b | CASE-010 | 9/9 | appeal | appeal | yes | — |
| qwen2.5:7b | CASE-013 | 7/9 | bill_patient | gather_documentation | no | — |
| qwen2.5:7b | CASE-020 | 8/9 | appeal | appeal | yes | — |
