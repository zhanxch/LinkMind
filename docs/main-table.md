# Paper main table

Each cell is **Score / success rate (%)**, equally averaged over standard and randomized scenes. The mean row weights all 12 tasks equally. Bold marks the highest distinct value and underline the second-highest, separately for each metric; ties share ranks. Baseline precision and published mean values are retained.

This is a transcription of the saved paper main table, not a new evaluation of the integrated release. Unreported tasks follow the paper's **0.0 / 0.0 filling convention** and are included in its mean; these zeros do not establish measured failures. Local evaluations and public leaderboard submissions are not seed-matched.

| Task | WALL-OSS 1.0-lite | VPP2 | OpenWAM-alpha | Pi-05 | PyRUA-Lean | HexaShell-Preview | GPT-6-Astra | LinkMind |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stack bowls | 85.9 / 84.0 | 55.6 / 48.0 | 49.9 / 45.3 | 45.1 / 38.0 | 73.9 / 70.0 | <ins>86.9</ins> / <ins>86.0</ins> | 66.5 / 62.0 | **94.9** / **94.0** |
| Push-T | 3.3 / 3.3 | 1.3 / 1.3 | 0.0 / 0.0 | 0.0 / 0.0 | 86.0 / 86.0 | <ins>96.0</ins> / <ins>96.0</ins> | 60.0 / 60.0 | **100.0** / **100.0** |
| Pack objects into box | 33.2 / 8.7 | 30.4 / 6.7 | 22.5 / 4.7 | 19.1 / 2.7 | **46.0** / **30.0** | 33.1 / 16.0 | 11.6 / 0.0 | <ins>43.5</ins> / <ins>26.0</ins> |
| Fold clothes | **87.5** / **84.7** | 70.8 / 68.0 | 57.5 / 55.3 | 32.3 / 24.0 | 59.2 / 52.0 | 47.6 / 40.0 | 76.4 / 72.0 | <ins>78.0</ins> / <ins>74.0</ins> |
| Hang mugs | 38.8 / 22.7 | <ins>43.9</ins> / **32.0** | 16.3 / 5.3 | 7.3 / 0.0 | 27.7 / 12.0 | 19.0 / 4.0 | 0.9 / 0.0 | **44.7** / <ins>26.0</ins> |
| Sweep blocks | 9.3 / 9.3 | <ins>10.7</ins> / <ins>10.7</ins> | 1.3 / 1.3 | 0.0 / 0.0 | 6.0 / 6.0 | 8.0 / 8.0 | 4.0 / 4.0 | **24.0** / **24.0** |
| Pour liquid into cup | **64.0** / **64.0** | <ins>50.0</ins> / <ins>50.0</ins> | 34.7 / 34.7 | 14.7 / 14.7 | 4.0 / 4.0 | 2.0 / 2.0 | 4.0 / 4.0 | 0.0 / 0.0 |
| Make toast | 26.0 / 13.3 | **50.0** / **39.3** | 12.5 / 2.7 | 6.0 / 0.7 | 21.5 / 14.0 | 1.5 / 0.0 | 0.5 / 0.0 | <ins>37.0</ins> / <ins>30.0</ins> |
| Arrange largest number | 38.2 / 24.0 | 8.3 / 2.0 | 4.9 / 0.7 | 2.8 / 0.7 | **80.1** / **74.0** | 30.2 / 22.0 | <ins>68.7</ins> / <ins>60.0</ins> | 65.7 / 56.0 |
| Sort nesting dolls by size | 48.0 / 48.0 | 18.7 / 18.7 | 4.7 / 4.7 | 5.3 / 5.3 | <ins>70.0</ins> / <ins>70.0</ins> | 52.0 / 52.0 | 18.0 / 18.0 | **82.0** / **82.0** |
| Store laptop and headphones | **50.4** / <ins>22.0</ins> | <ins>45.3</ins> / **32.7** | 30.5 / 16.0 | 16.1 / 5.3 | 4.8 / 0.0 | 4.8 / 0.0 | 1.6 / 0.0 | 0.0 / 0.0 |
| Stack blocks | 75.2 / 71.3 | 51.7 / 44.7 | 13.7 / 7.3 | 11.9 / 6.7 | **100.0** / **100.0** | 89.5 / 88.0 | 88.1 / 86.0 | <ins>93.2</ins> / <ins>92.0</ins> |
| Mean (12 tasks) | 46.7 / 37.9 | 36.4 / 29.5 | 20.7 / 14.8 | 13.4 / 8.2 | <ins>48.3</ins> / <ins>43.2</ins> | 39.2 / 34.5 | 33.4 / 30.5 | **55.3** / **50.3** |

The VLA/WAM columns are WALL-OSS 1.0-lite, VPP2, OpenWAM-alpha and Pi-05; the remaining columns are agent methods. Baselines are transcribed from the paper's recorded RoboDojo-Sim leaderboard / GPT-6-Astra evaluation sources, not refreshed from today's leaderboard.

## Evidence and scope

- The paper reports **Push-T 100.0 / 100.0**. The separately archived local toolkit run has **48 successes and 2 unscored scenes**; its confirmed success fraction is 96%, and success among its 48 scored attempts is 100%. These are different reporting scopes; this release does not claim a new 50/50 toolkit run.
- Arrange largest number (65.7 / 56.0) and Sort nesting dolls by size (82.0 / 82.0) are author-supplied paper results. Their native reports are not included in the local eight-task evidence package.
- Pour liquid into cup and Store laptop and headphones use the paper's unreported-task zero-fill convention.
- See [local native evidence](local-results.md) for per-task commits, budgets, failures, interruptions and supplements. That table preserves missing scores separately.
- The main-table source was the locally saved paper checkout `f0f352e6b2a908f2d09ea6e5b2f4f835609e442e`. An authenticated Overleaf refresh was unavailable at release preparation; this does not certify the currently displayed online manuscript.

[Machine-readable table](../results/paper-main-table.json) · [CSV](../results/paper-main-table.csv). The JSON records source hashes. Only the table data and a newly written method explanation are published; manuscript text, TeX and PDFs are excluded.
