# Engineering decisions

## Time weighting instead of a row average

A logger may record faster during one part of a run than another. A simple mean gives the densely sampled part disproportionate influence. TraceDrive integrates sampled absolute and squared errors with the trapezoidal rule and divides by elapsed time. This still approximates behavior between samples; a long unobserved gap remains uncertainty rather than evidence.

The test `test_irregular_sampling_uses_time_instead_of_sample_count` checks a deliberately uneven trace against hand-calculated MAE and RMSE. A constant timestamp offset changes neither metric.

## Reject an invalid run instead of silently cleaning it

Dropped rows, guessed units, and reordered timestamps can conceal a logging problem. CSV ingestion therefore rejects the complete run, names the physical CSV row and column where possible, and writes nothing until parsing and analysis succeed. An explicit preprocessing stage could be added later, preserving both the original file and a transformation log.

## Event windows rather than isolated colored points

Consecutive threshold violations are grouped so a person can inspect a period. Window endpoints are actual samples. No threshold-crossing time is invented, and no label claims a motor, battery, or controller failure. Simultaneous battery and velocity excursions are a reason to investigate, not proof of causation.

## SQLite and immutable run records

SQLite is enough for a local tool and makes a run durable across restarts without a database service. Each record contains metadata, validated samples, and derived anomalies together. Every operation gets a short-lived connection that is closed explicitly. A write transaction inserts the whole run; demo seeding uses `BEGIN IMMEDIATE` so concurrent seed requests cannot duplicate the dataset.

Storing samples as JSON favors a straightforward run-level interface. It does not provide efficient SQL queries across millions of samples. A larger system could use a separate sample table, a columnar file format, or a time-series store, after measuring its access patterns.

## A small API with a separate analysis layer

CSV parsing and analysis can be exercised without HTTP or SQLite. The storage layer is independent of the browser, and the browser uses the same JSON routes exposed to a script. This lets tests distinguish a math error from an HTTP integration error.

## Local-only by default

The built-in HTTP server listens on loopback. JSON writes reject unexpected content types; requests are bounded, SQL uses parameters, and static paths stay inside the web directory. These safeguards support local use. Public deployment would need a production server, authentication, authorization, TLS, rate limits, operational monitoring, and a separate review.

## Deliberate limits

The dashboard uses fixed illustrative thresholds so the first version is easy to reproduce. Configurable per-robot profiles should persist their units, calibration, and threshold version alongside every analysis. Existing results should not silently change when a profile is edited.
