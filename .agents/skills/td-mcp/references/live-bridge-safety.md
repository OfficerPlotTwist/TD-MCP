# Live bridge safety

Follow the save/edit/verify/save discipline in `AGENTS.md`. Create a new unused project file or a COMP checkpoint before mutation, preserving existing restore points. Do not assume `project.saveBackup()` exists. Verify the actual save path because TD may increment explicit filenames.

Use `save_checkpoint(name='pre_change', op_path='<affected COMP>', description='Before scoped change')` before bulk edits. The Node host and TD must share access to the checkpoint directory. A COMP snapshot omits unrelated project/global settings.

Never restart/deactivate/replace the serving WebServer DAT through MCP. Never combine bulk destroy with force-cook. Keep changes small and inspect errors and TOP output before saving a finished version.

New callback source executes scripts with one request-local namespace so nested functions resolve script imports and variables. An older installed callback may retain the separate-scope bug: use iterative walks or explicitly passed variables there. `COMP.children` is a list.

A timeout is not a rollback. Check the live project/operator state before retrying any mutation. Report disk evidence separately from live verification.
