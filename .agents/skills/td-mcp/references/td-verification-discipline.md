# Visual verification

Do not infer visual correctness from source, no errors, or successful file creation. Inspect the relevant live TOP output before claiming it looks correct; arbitrary panel UI cannot be captured by `take_screenshot`.

Inspect corners and edges as well as the center. Check for uniform failed tiles, wrong grid placement, repeated inputs, wrong-stage connections, and unexpected network imagery. For multipass work, save labeled input/output images at each meaningful stage and a parameter/seed manifest. Review images must open without rerunning processing.

For browser-backed panels, compare actual container, browser, and Web Render dimensions. Preserve aspect (`topfill='best'` where supported), synchronize sizes, and map pointer input through letterboxing. A CSS check alone cannot establish that controls are undistorted.

State structural, numeric, screenshot, panel, and hardware verification separately. Offline renders do not prove live integration; a network send does not prove physical output. When capture is unavailable, name the missing evidence plainly.
