# Approval Boundaries in TouchDesigner MCP

The MCP tools require approval for mutating operations (`execute_script`, `set_par_value`, `create_operator`, `connect_operators`, `disconnect_operators`, `delete_operator`). This is appropriate for structural changes. It is **not** appropriate for trivial parameter adjustments where the correct value is obvious and the user's intent is clear.

## Act without asking when

### Single parameter to a known value
The user says "set X to Y" — just do it. Don't ask "shall I set X to Y?"

```python
# User: "change noise_demo period to 0.5"
# DO: set_par_value('/project1/noise_demo', 'period', 0.5)
# DON'T: "I'll need to set the period parameter. Should I proceed?"
```

### Fixing a wrong value you just set
If you set a parameter and the user says "no, it should be Z" — change it. Don't ask for approval to fix your own mistake.

### Resolution / pixel format switches
The user says "change to nearest pixel" or "set to 32-bit float" — these are one-parameter changes with known values. Execute immediately.

### Obvious defaults from context
When the user's intent is unambiguous from context ("make it brigher" → increase intensity/exposure by a reasonable step), act. Don't solicit a value.

## Ask when

### Destructive structural changes
- Deleting operators the user didn't explicitly name
- Rewiring connections you're unsure about
- Mass parameter rewrites across many operators

### Ambiguous intent
When the user's request could reasonably mean two different things and both are plausible, ask which one.

### The user explicitly says "ask before..."
If the user sets a boundary, respect it.

## The pattern this replaces

Prompt 147: "you don't need my go ahead to change to nearest pixl. adjust perms"

The model asked for approval on a trivial one-parameter change where the user had explicitly stated the desired value. The correct behavior: execute the change, report the result. The approval gate is for the user's protection, not a speed bump on every parameter touch.
