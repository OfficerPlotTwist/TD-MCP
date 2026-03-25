# TouchDesigner Troubleshooting Guide

## MCP Integration Issues

### Problem: MCP Tools Return 404 Errors

**Symptoms:**
- All MCP TouchDesigner tools fail
- Error message: "Request failed with status code 404"
- Tools affected: `create_operator`, `execute_python`, `get_operator_info`, etc.

**Root Cause:**
MCP server routing/endpoint configuration issue

**Solution:**
✅ **Use HTTP POST workaround instead of MCP tools**

```powershell
# Instead of MCP tools, use direct HTTP:
$body = @{ script = 'your_python_code' } | ConvertTo-Json
$response = Invoke-WebRequest -Uri http://127.0.0.1:9980/execute `
    -Method POST -Body $body `
    -ContentType 'application/json' -UseBasicParsing
$json = $response.Content | ConvertFrom-Json
```

**Status:** Permanent workaround - MCP tools will not be fixed

---

## API Parameter Issues

### Problem: Wrong Parameter Name

**Symptoms:**
- Request succeeds but no output
- TouchDesigner doesn't execute code

**Root Cause:**
Using `code` parameter instead of `script`

**Solution:**
```powershell
# ❌ Wrong:
$body = @{ code = 'print("test")' }

# ✅ Correct:
$body = @{ script = 'print("test")' }
```

---

## Unicode Character Errors

### Problem: GLSL Files Fail to Parse

**Symptoms:**
- Error: "utf-8 codec can't decode byte"
- Occurs when sending GLSL files
- Position mentioned in error (e.g., "position 371")

**Root Cause:**
GLSL files contain Unicode characters (em-dashes, smart quotes)

**Solution:**
Replace Unicode characters before sending:

```powershell
$glslContent = Get-Content -Path $file -Raw -Encoding UTF8
$glslContent = $glslContent -replace [char]0x2014, '-'  # em dash
$glslContent = $glslContent -replace [char]0x2013, '-'  # en dash
$glslContent = $glslContent -replace [char]0x201C, '"'  # left double quote
$glslContent = $glslContent -replace [char]0x201D, '"'  # right double quote
$glslContent = $glslContent -replace [char]0x2018, "'"  # left single quote
$glslContent = $glslContent -replace [char]0x2019, "'"  # right single quote
```

---

## Operator Creation Issues

### Problem: Operators Created at Root Instead of Project

**Symptoms:**
- Operators appear at `/` level
- Not inside `/project1` container

**Root Cause:**
Using `op('/')` as parent instead of `op('/project1')`

**Solution:**
```python
# ❌ Wrong:
parent = op('/')
new_op = parent.create(noiseTOP, 'noise1')

# ✅ Correct:
parent = op('/project1')
new_op = parent.create(noiseTOP, 'noise1')
```

---

## Response Parsing Issues

### Problem: Output Shows ASCII Codes

**Symptoms:**
- Response displays as numbers: `123 34 111 117...`
- Can't read actual output

**Root Cause:**
PowerShell displaying raw bytes instead of parsed JSON

**Solution:**
```powershell
# Parse JSON and access .output property:
$json = $response.Content | ConvertFrom-Json
Write-Host $json.output  # Shows actual text
```

---

## Connection Issues

### Problem: Cannot Connect to TouchDesigner

**Symptoms:**
- Connection refused
- Timeout errors
- 404 on endpoint

**Checklist:**
1. ✅ TouchDesigner is running
2. ✅ Web Server DAT exists and is active
3. ✅ Port is set to 9980
4. ✅ Firewall allows port 9980
5. ✅ Using correct endpoint: `http://127.0.0.1:9980/execute`

**Test Connection:**
```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 9980
```

---

## Empty Response Issues

### Problem: Response is Empty or Null

**Symptoms:**
- `$json.output` is empty
- No errors reported

**Root Cause:**
Python code doesn't print anything

**Solution:**
```python
# Add print statements:
op_node = op('/project1/noise1')
print(f'Found operator: {op_node}')  # This will appear in output
```

---

## Timing Issues

### Problem: Operations Fail Intermittently

**Symptoms:**
- Sometimes works, sometimes doesn't
- Errors about operators not found

**Root Cause:**
Operations executing too quickly

**Solution:**
Add delays between operations:

```powershell
Invoke-TDScript -Script $script1
Start-Sleep -Milliseconds 300  # Wait before next operation
Invoke-TDScript -Script $script2
```

---

## Debugging Tips

### Enable Verbose Output
```powershell
$VerbosePreference = "Continue"
# Your script here
```

### Check Both Output and Errors
```powershell
$json = $response.Content | ConvertFrom-Json
Write-Host "Output: $($json.output)"
Write-Host "Errors: $($json.errors)"
```

### Verify Operator Exists
```python
op_node = op('/project1/my_operator')
if op_node:
    print(f'Operator exists: {op_node.path}')
else:
    print('Operator not found!')
```

### List All Operators
```python
ops = op('/project1').children
print('Operators in /project1:')
for o in ops:
    print(f'  {o.name} ({o.type})')
```

---

## Getting Help

1. Check [API Reference](api-reference.md) for correct syntax
2. Review [Examples](examples/) for working code
3. Verify [Setup](../workflows/touchdesigner-setup.md) is correct
4. Check [.cline/touchdesigner-context.md](../.cline/touchdesigner-context.md) for AI assistant context
