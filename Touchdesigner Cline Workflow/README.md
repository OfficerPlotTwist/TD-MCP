# TouchDesigner Workflows

Streamlined workflows and utilities for TouchDesigner automation via HTTP API.

## Quick Start

### Prerequisites
1. **TouchDesigner** must be running
2. **Web Server DAT** configured on port 9980
3. **Project container** exists (default: `/project1`)

### Setup Web Server DAT
1. Create a Web Server DAT in TouchDesigner
2. Set port to `9980`
3. Enable the server
4. Test endpoint: `http://127.0.0.1:9980/execute`

## ⚠️ Critical: MCP Workaround

**The TouchDesigner MCP tools have 404 errors and DO NOT WORK.**

### Working Solution
Use direct HTTP POST requests instead:

```powershell
$body = @{
    script = 'print("Hello from TouchDesigner")'
} | ConvertTo-Json

$response = Invoke-WebRequest -Uri http://127.0.0.1:9980/execute `
    -Method POST -Body $body `
    -ContentType 'application/json' -UseBasicParsing

$json = $response.Content | ConvertFrom-Json
Write-Host $json.output
```

**Key Points:**
- Parameter is `script` NOT `code`
- Always create operators in `/project1` container
- Replace Unicode characters in GLSL files before sending

## Common Tasks

### Create an Operator
```powershell
.\scripts\templates\create-operator.ps1 -Type "noiseTOP" -Name "noise1"
```

### Import GLSL Shaders
```powershell
.\workflows\glsl-pipeline.ps1 -Directory "path/to/glsl/files"
```

### Setup Camera Look At
```powershell
.\scripts\camera-lookat.ps1 -Position "0,3,5" -Target "0,0,0"
```

## File Structure

```
Touchdesigner/
├── README.md                      # This file
├── touchdesigner.config.json      # Configuration settings
├── .vscode/settings.json          # VS Code workspace settings
├── .cline/touchdesigner-context.md # AI assistant context
├── workflows/                     # Reusable workflow templates
│   ├── touchdesigner-setup.md
│   ├── create-operators.workflow
│   └── glsl-pipeline.workflow
├── scripts/                       # PowerShell utilities
│   └── templates/                 # Reusable script templates
│       ├── http-request.ps1
│       ├── create-operator.ps1
│       └── verify-operator.ps1
└── docs/                          # Documentation
    ├── troubleshooting.md
    ├── api-reference.md
    ├── mcp-workaround.md
    └── examples/
```

## Troubleshooting

### MCP 404 Errors
**Problem:** MCP tools return 404 errors  
**Solution:** Use HTTP POST workaround (see above)

### Unicode Character Errors
**Problem:** GLSL files with special characters fail  
**Solution:** Replace em-dashes, smart quotes before sending (see `touchdesigner.config.json`)

### Operators Created at Root
**Problem:** Operators appear at `/` instead of in project  
**Solution:** Always use `op('/project1')` as parent

See [docs/troubleshooting.md](docs/troubleshooting.md) for more details.

## Configuration

Edit `touchdesigner.config.json` to customize:
- API endpoint and timeout
- Default container path
- Operator spacing
- Unicode character replacements

## Documentation

- [API Reference](docs/api-reference.md) - TouchDesigner API patterns
- [MCP Workaround](docs/mcp-workaround.md) - Detailed HTTP solution
- [GLSL Workflows](docs/glsl-workflows.md) - Shader-specific workflows
- [Examples](docs/examples/) - Working code examples

## Contributing

When adding new workflows:
1. Create template in `workflows/`
2. Add reusable scripts to `scripts/templates/`
3. Document in `docs/`
4. Update this README

## License

MIT
