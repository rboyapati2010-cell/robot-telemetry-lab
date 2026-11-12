# Learn and extend TraceDrive

These exercises are development tasks, not claims about work already completed on a real robot.

## Understand the current implementation

1. Run the tests and locate the hand-calculated uneven-sampling example. Compute its MAE and RMSE yourself.
2. Trace an import from `server.py` through `parse_csv`, `analyze`, and `Store.add`. Identify where an invalid row stops the write.
3. Explain why a one-sample anomaly has zero observed duration and why that does not mean the event lasted zero seconds.
4. Start the server with a temporary database. Import a run, restart the process, and retrieve the same run ID.
5. Compare a run to itself and inspect why every delta is zero.

## Make an original contribution

Choose one change, define the expected behavior, write a meaningful test, implement it, and record what you learned:

- **Your own robot data:** export a short, non-sensitive log with documented sensor units. Map it to the CSV schema and describe the conditions of the experiment. Get permission before publishing team data.
- **Sampling-quality report:** flag unusually large time gaps and report median and maximum intervals. Test a sparse log and explain the threshold choice.
- **Robot profiles:** persist named threshold/calibration profiles and store which version was used for each analysis.
- **A new signal:** add angular velocity or heading error, including units, bounds, metrics, visualization, and parser tests.
- **A fair comparison:** conduct repeated runs of the same task. State what was controlled, what changed, and what the data cannot establish.

## Questions to be ready to answer

- Why use SQLite here rather than a hosted database?
- Why not average the errors directly?
- Which errors do you reject instead of repairing automatically?
- What happens if two clients seed the demo at the same time?
- What does an improvement in MAE fail to tell you?
- Which parts were AI-assisted, and what have you personally verified or changed?

Keep a short development log describing your own decisions and tests. Use only those verified contributions in an application or interview.
