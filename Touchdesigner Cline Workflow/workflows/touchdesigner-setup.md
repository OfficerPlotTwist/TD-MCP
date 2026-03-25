# TouchDesigner Workflow Setup

## Prerequisites Checklist

- [ ] TouchDesigner installed and running
- [ ] Web Server DAT created and configured
- [ ] Project container exists (default: `/project1`)
- [ ] Port 9980 is available and not blocked by firewall

## Step 1: Configure Web Server DAT

1. **Create Web Server DAT**
   - In TouchDesigner, create a new `webserverDAT`
   - Name it `webserver1` or similar

2. **Configure Settings**
   ```
   Port: 9980
   Active: ON
   ```

3. **Test Endpoint**
   - Open browser to: `http://127.0.0.1:9980`
   - Should see TouchDesigner web interface

## Step 2: Test API Connection

Run this PowerShell command to test:

```powershell
$body = @{ script = 'print("API Working!")' } | ConvertTo-Json
$response = Invoke-WebRequest -Uri http://127.0.0.1:9980/execute -Method POST -Body $body -ContentType 'application/json' -UseBasicParsing
($response.Content | ConvertFrom-Json).output
```

Expected output: `API Working!`

## Step 3: Verify Project Container

```powershell
$body = @{ script = 'print(op("/project1"))' } | ConvertTo-Json
$response = Invoke-WebRequest -Uri http://127.0.0.1:9980/execute -Method POST -Body $body -ContentType 'application/json' -UseBasicParsing
($response.Content | ConvertFrom-Json).output
```

If `/project1` doesn't exist, create it in TouchDesigner.

## API Configuration

### Endpoint Details
- **URL**: `http://127.0.0.1:9980/execute`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **Body Parameter**: `script` (NOT `code`)

### Request Format
```json
{
  "script": "python_code_here"
}
```

### Response Format
```json
{
  "output": "printed_output_here",
  "errors": []
}
```

## Common Issues

### Issue: 404 Error
**Cause**: Web Server DAT not running or wrong port  
**Solution**: Check Web Server DAT is active on port 9980

### Issue: Connection Refused
**Cause**: TouchDesigner not running  
**Solution**: Start TouchDesigner first

### Issue: Empty Response
**Cause**: Python code has no print statements  
**Solution**: Add `print()` statements to see output

## Next Steps

Once setup is complete:
1. Review [API Reference](../docs/api-reference.md)
2. Try [Example Workflows](../docs/examples/)
3. Create your first operator with `scripts/templates/create-operator.ps1`
