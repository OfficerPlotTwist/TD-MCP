# TD Crash Recovery

TouchDesigner can freeze or crash, especially during bulk operations, Blender rendering, or heavy GPU work. When the user reopens TD (or says "reopened td", "we crashed", "touchdesigner is frozen", "computer crashed"), follow this recovery protocol **before doing anything else**.

## Recovery Protocol

### 1. Check project state
```python
list_operators('/project1')
```
Compare against what you remember was built. If a component the user expects is missing, it was lost in the unsaved session.

### 2. Restore from backups if available
- Check `checkpoints/` for `.tox` snapshots that cover the missing operators.
- Check `toe/Backup/` for TD auto-backups (`nightbefore` files). The latest is usually the most recent save before crash.
- If the user names a specific component ("cam_orbit", "cont_uidemo"), search checkpoints first.

### 3. Save immediately after confirming state
```python
execute_script("project.save()")
```
Do this before any edits. The reopened session is unsaved; a second crash loses everything again.

### 4. Report what was lost and what survived
Tell the user explicitly:
- What operators are present and match expectations
- What's missing (by name if you know it)
- Whether a checkpoint covers the missing work
- Whether you need to rebuild from scratch

### 5. Rebuild from checkpoints when available
If a `save_checkpoint` was created before the work that was lost:
```python
restore_checkpoint('<checkpoint_name>')
```
Then verify with `get_operator_info` and `get_errors`.

### Lost work without a checkpoint
When the user asks to rebuild something that has no checkpoint, save the project first, then rebuild. This time, create a checkpoint before starting:
```python
save_checkpoint('/project1', 'pre_rebuild_<component>', 'Before rebuilding <component> after crash')
```

## The pattern this replaces

Before this protocol existed, every TD restart triggered the same loop:
- User: "reopened td. check project state"
- Model: *checks, finds missing ops, asks what to do*
- User: "restore missing" or "impliment camera again, its missing bc no save"

The protocol short-circuits this: check, restore, save, report. No asking.
