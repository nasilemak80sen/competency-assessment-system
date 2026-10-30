# OpenGlobus nationality frontend

This directory contains the browser-side implementation for the Streamlit
nationality globe. Python reads these assets and embeds them in the iframe;
the POC has no Node build step.

## Files

- \`index.html\`: iframe structure and accessible UI shell.
- \`styles.css\`: globe overlays, toolbar, details panel and responsive styling.
- \`contract.js\`: browser-side validation of the Python JSON contract.
- \`filters.js\`: employment category, salary grade and section filters.
- \`markers.js\`: proportional marker SVG generation.
- \`layers.js\`: OpenGlobus Entity and Vector layer management.
- \`details.js\`: safe DOM-based detail panel rendering.
- \`camera.js\`: camera flight behaviour.
- \`main.js\`: engine initialization, event wiring and lifecycle/error states.

## Data flow

\`services.geospatial_service.build_nationality_dataset()\` owns nationality
normalisation, aggregation, coordinate validation and the versioned contract.
This frontend does not query Excel, SQLite or any other data source.
\`components.openglobus\` is only the Streamlit iframe adapter.

## Contract version 1

The payload has \`schemaVersion: 1\`, \`datasetType:
"nationality-distribution"\`, a \`summary\`, and \`records\`. Each record has
\`id\`, \`nationality\`, authoritative \`personnelCount\`, \`latitude\`,
\`longitude\`, \`representationPct\`, \`representationDisplay\`, and a \`people\`
array. Personnel detail objects contain only \`name\`, \`staffPosition\`,
\`department\`, \`salaryGrade\`, \`employmentCategory\`, and \`sectionName\`.
Staff IDs and unrelated HR fields are not sent to the browser.

Unfiltered marker counts use the aggregate \`personnelCount\`. Active browser
filters count matching personnel detail rows, so the detail rows must cover
the population for filtered counts to be complete.

## Extension guidance

Keep workbook/database reconciliation and geospatial transformations in the
Python service. Add visual layers as separate frontend modules consuming this
renderer-neutral contract or a future versioned feature collection. Do not put
SQL, workbook parsing or personnel reconciliation in this frontend.

## Browser tests

\`tests/test_v2_openglobus_browser.py\` uses Chromium with a controlled engine
test double. It verifies iframe lifecycle, marker/entity creation, filters,
picking, details, camera calls and module-load failure. This verifies the
application integration, not the real engine's GPU rendering. Also perform a
manual visual smoke test against the pinned OpenGlobus CDN and live map tiles.
