# Live Bridge Safety

The TD MCP bridge mutates a live, usually unsaved TouchDesigner session. Changes are immediate in memory but are not durable until `project.save()` runs.

Before the first mutating edit in a task, run:

```python
project.save()
```

For experiments, bulk destructive work, containerization, or mass parameter rewrites, save a checkpoint on the parent COMP first with the MCP `save_checkpoint` tool.

After edits:

1. Check recent errors with `get_errors`.
2. Inspect changed operators with `get_operator_info`.
3. Inspect important parameters with `get_par_value`.
4. Capture relevant TOP output with `take_screenshot` when the visual result is TOP-renderable.
5. Run `project.save()` only after verification passes.

Do not combine bulk destruction with force-cooking in the same script. This can freeze TouchDesigner.

Never activate Start, Restart, or server-control buttons on `/project1/TD_MCP`; doing so can reinitialize the WebServer DAT and disconnect the MCP bridge mid-task. It is acceptable to create or inspect those controls structurally.

When creating new disconnected or top-level COMPs, set `nodeX` and `nodeY` away from the existing network cluster so the patch remains readable. Network position is not panel position.

`execute_script` scoping gotcha: scripts run in a wrapper where nested functions cannot reliably see top-level locals. Avoid recursion and closures over outer locals. Prefer iterative tree walks with explicit stacks or queues.
