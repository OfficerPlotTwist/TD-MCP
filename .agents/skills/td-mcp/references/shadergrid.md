# Candidate review grids

This is an optional authoring pattern, not a bridge dependency. Choose candidates from the current task's source; record candidate IDs, tile positions, parameters, failures, and human choices in a manifest alongside saved review images.

Use numbered tiles and explicit row/column indexing. Inspect edges, corners, repeated inputs, uniform failed tiles, and stage ordering. Save images that can be opened without rerunning a shader or processing pipeline. Do not carry approval commands, rankings, or source pools from a different project.

Respect requested human selection before continuing dependent rendering. A completed background job is not a human selection.
