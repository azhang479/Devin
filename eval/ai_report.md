## AI evidence-matching evaluation

Cases were hand-authored to include paraphrases and negations; they are not a sample of real clinical notes.

| Method | Action accuracy | TP | FP | FN | Precision | Recall | Rejected quotes | Mean seconds/case | Max seconds/case |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Keyword | 4/12 (33.3%) | 4 | 6 | 12 | 40.0% | 25.0% | 0 | 0.00 | 0.00 |
| qwen2.5:3b | 11/12 (91.7%) | 13 | 0 | 3 | 100.0% | 81.2% | 0 | 5.13 | 8.41 |
| qwen2.5:7b | 12/12 (100.0%) | 13 | 1 | 3 | 92.9% | 81.2% | 0 | 12.64 | 19.54 |

| Case | Expected action | Keyword action | qwen2.5:3b AI action | qwen2.5:7b AI action |
|---|---|---|---|---|
| AI-01 | appeal | gather_documentation | appeal | appeal |
| AI-02 | gather_documentation | appeal | gather_documentation | gather_documentation |
| AI-03 | appeal | gather_documentation | gather_documentation | appeal |
| AI-04 | appeal | gather_documentation | appeal | appeal |
| AI-05 | gather_documentation | appeal | gather_documentation | gather_documentation |
| AI-06 | appeal | gather_documentation | appeal | appeal |
| AI-07 | gather_documentation | gather_documentation | gather_documentation | gather_documentation |
| AI-08 | appeal | gather_documentation | appeal | appeal |
| AI-09 | gather_documentation | gather_documentation | gather_documentation | gather_documentation |
| AI-10 | appeal | appeal | appeal | appeal |
| AI-11 | gather_documentation | gather_documentation | gather_documentation | gather_documentation |
| AI-12 | gather_documentation | appeal | gather_documentation | gather_documentation |
