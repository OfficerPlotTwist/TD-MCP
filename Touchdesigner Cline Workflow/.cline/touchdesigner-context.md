# TouchDesigner Context for AI Assistants

## ⚠️ CRITICAL: MCP Tools DO NOT WORK

**All TouchDesigner MCP tools return 404 errors. DO NOT attempt to use:**
- `create_operator`
- `execute_python`
- `get_operator_info`
- `set_parameter`
- `get_parameter`
- `delete_operator`
- `list_operators`
- `get_project_info`

## ✅ Working Solution: HTTP POST API

### Endpoint Configuration
```
URL: http://127.0.0.1:9980/execute
Method: POST
Content-Type: application/json
Body: {"script": "python_code_here"}
```

### PowerShell Template
```powershell
$body = @{
    script = 'your_python_code_here'
} | ConvertTo-Json

$response = Invoke-WebRequest -Uri http://127.0.0.1:9980/execute `
    -Method POST -Body $body `
    -ContentType 'application/json' -UseBasicParsing

$json = $response.Content | ConvertFrom-Json
Write-Host $json.output
```

## Key Rules

### 1. Parameter Name
- ✅ Use `script` parameter
- ❌ NOT `code` parameter

### 2. Container Path
- ✅ Always create in `/project1`: `op('/project1').create(...)`
- ❌ NOT at root: `op('/').create(...)`

### 3. Unicode Characters
Replace before sending GLSL files:
```powershell
$content -replace [char]0x2014, '-'  # em dash
$content -replace [char]0x2013, '-'  # en dash
$content -replace [char]0x201C, '"'  # left double quote
$content -replace [char]0x201D, '"'  # right double quote
$content -replace [char]0x2018, "'"  # left single quote
$content -replace [char]0x2019, "'"  # right single quote
```

### 4. Response Parsing
```powershell
$json = $response.Content | ConvertFrom-Json
$output = $json.output  # Actual output
$errors = $json.errors  # Error array
```

## Common Patterns

### Create Operator
```python
parent = op('/project1')
new_op = parent.create(operatorType, 'name')
new_op.nodeX = 100
new_op.nodeY = 200
print(f'Created: {new_op.path}')
```

### Connect Operators
```python
source = op('/project1/source_op')
target = op('/project1/target_op')
target.inputConnectors[0].connect(source)
```

### Set Parameters
```python
op_node = op('/project1/my_op')
op_node.par.parametername = value
op_node.par.tx = 5  # position
op_node.par.lookat = 1  # enable
```

### Camera Look At
```python
cam = op('/project1/cam1')
cam.par.tx = 0
cam.par.ty = 3
cam.par.tz = 5
cam.par.lookat = 1
cam.par.lookatpath = '/project1/target'
```

### GLSL Setup
```python
parent = op('/project1')
glsl_top = parent.create(glslTOP, 'shader_name')
text_dat = parent.create(textDAT, 'shader_name_pixel')
text_dat.text = '''glsl_code_here'''
glsl_top.par.pixeldat = text_dat
```

## Debugging Tips

1. **Check Response**: Always check both `.output` and `.errors`
2. **Verify Operators**: Use `op('/path')` to check if operator exists
3. **Print Statements**: Add `print()` for debugging
4. **Delays**: Add `Start-Sleep -Milliseconds 300` between operations

## Configuration Files

- `touchdesigner.config.json` - API settings, defaults, operator types
- `.vscode/settings.json` - Workspace settings with custom instructions
- `README.md` - Quick start and troubleshooting

## Quick Reference

**Operator Types:**
- TOP: noiseTOP, glslTOP, moviefileinTOP, renderTOP
- CHOP: constantCHOP, mathCHOP, noiseCHOP
- SOP: boxSOP, sphereSOP, gridSOP
- COMP: cameraCOMP, lightCOMP, geometryCOMP
- DAT: textDAT, tableDAT, scriptDAT

**Common Parameters:**
- Position: tx, ty, tz
- Rotation: rx, ry, rz
- Scale: sx, sy, sz
- Camera: lookat, lookatpath, fov
- GLSL: pixeldat, vertexdat, computedat

## Workflow Pattern

1. Create operators via HTTP POST
2. Verify creation with follow-up query
3. Set parameters and connections
4. Rename for clarity
5. Document in README

## When Starting a New Session

Always include this context:
> "TouchDesigner MCP tools have 404 errors. Use HTTP POST to http://127.0.0.1:9980/execute with 'script' parameter. Create operators in /project1. Replace Unicode chars in GLSL files."
