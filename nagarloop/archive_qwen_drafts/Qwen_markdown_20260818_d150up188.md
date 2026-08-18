## CODE STYLE — HUMAN-FIRST ✅
- Standard, boring, readable code: clear names, one job per function, normal loops.
- SHORTEST version that stays clear. If 10 lines do it, never write 40.
- No over-engineering: no extra abstractions, decorators, factories, or enterprise patterns for a demo.
- if/elif over nested ternaries. Dicts over long repeated code. Constants at top of file.
- Comments only for WHY. Section headers so a human can navigate the file.
- Used once → inline it. Used 3+ times → small function.
- Every file must stay editable by a beginner.