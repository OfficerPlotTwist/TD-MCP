# Optional shared controls

Tone tools analyze explicitly supplied row/column CHOP paths and return rule matches. A rule's `skill` field is a descriptive action label, not an installed or automatically executed agent skill.

For projects that need image-driven controls, use a role-named Null CHOP as the stable shared handoff and drive target parameters by expression or binding to its semantic channels. Discover or create the handoff within the relevant project component; no global path is required. Keep fixed/manual controls fixed unless the task calls for analysis-driven behavior.

Tone rules are optional. Copy the generic bundled rules to an ignored local file and select it with `TD_TONE_RULES` before customizing; the bridge does not require an analysis network.
