# TouchDesigner Workflows - Quick Start

## 🚀 Get Started in 3 Steps

### 1. Setup TouchDesigner (One-time)
```
1. Open TouchDesigner
2. Create a Web Server DAT
3. Set port to 9980
4. Enable it
```

### 2. Test Connection
```powershell
cd "c:\Users\immer\Documents\Cline\Workflows\Touchdesigner"
. .\scripts\templates\http-request.ps1
Test-TDConnection
```

### 3. Create Your First Operator
```powershell
.\scripts\templates\create-operator.ps1 -Type "noiseTOP" -Name "noise1"
```

## 📋 Essential Files

| File | Purpose |
|------|---------|
| `README.md` | Full documentation |
| `touchdesigner.config.json` | API settings & defaults |
| `.vscode/settings.json` | Workspace configuration |
| `.cline/touchdesigner-context.md` | AI assistant context |
| `scripts/templates/http-request.ps1` | Reusable HTTP functions |
| `docs/troubleshooting.md` | Problem solutions |

## ⚠️ Critical Information

**MCP Tools Don't Work** - Use HTTP POST instead:
```powershell
$body = @{ script = 'print("Hello")' } | ConvertTo-Json
$response = Invoke-WebRequest -Uri http://127.0.0.1:9980/execute `
    -Method POST -Body $body -ContentType 'application/json' -UseBasicParsing
($response.Content | ConvertFrom-Json).output
```

**Key Points:**
- Parameter is `script` NOT `code`
- Create in `/project1` NOT `/`
- Replace Unicode chars in GLSL files
- Add 300ms delays between operations

## 📚 Learn More

- [Setup Guide](workflows/touchdesigner-setup.md)
- [API Reference](docs/api-reference.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Examples](docs/examples/)

## 🎯 Common Tasks

### Create Operator
```powershell
.\scripts\templates\create-operator.ps1 -Type "noiseTOP" -Name "noise1" -X 100 -Y 200
```

### Execute Python Code
```powershell
. .\scripts\templates\http-request.ps1
Invoke-TDScript -Script 'print(op("/project1").children)'
```

### Import GLSL Shaders
See [GLSL Shader Network Example](docs/examples/glsl-shader-network.md)

## 💡 Pro Tips

1. **Always source http-request.ps1** for reusable functions
2. **Check errors** with `$json.errors`
3. **Use print()** in Python to see output
4. **Add delays** between operations
5. **Read the context file** before starting new AI sessions
