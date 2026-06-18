# Expressive Controls

An Expressive control is a project control meant to react to the image-analysis or tone pipeline crossing a threshold. Tone rules live in `td-mcp-server/tone-rules.json` and can be inspected through MCP tone tools.

Route Expressive controls through the single aggregating CHOP:

```python
op('/project1/null_expressive')
```

Do not hardwire these parameter values directly on target operators. Drive target parameters by expression or binding to a channel on `/project1/null_expressive`.

Example:

```python
t.par.X.expr = "op('/project1/null_expressive')['feedbackbloom_threshold']"
```

Name channels by the purpose of the operator-tree subsection they drive, not the raw operator or parameter name. For example, prefer `feedbackbloom_threshold` for a feedback bloom threshold control.

Bias inclusive: when unsure whether a control is Expressive, route it through `null_expressive`. Over-routing is easier to undo than discovering later that tone-driven behavior bypasses the shared control path.
