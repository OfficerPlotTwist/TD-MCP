# Reusable HTTP Request Function for TouchDesigner API
# Source this file in other scripts: . .\scripts\templates\http-request.ps1

# Global configuration
$global:TD_ENDPOINT = "http://127.0.0.1:9980/execute"
$global:TD_TIMEOUT = 5000

<#
.SYNOPSIS
    Execute Python code in TouchDesigner via HTTP API
.DESCRIPTION
    Sends Python code to TouchDesigner's Web Server DAT and returns the response
.PARAMETER Script
    Python code to execute in TouchDesigner
.PARAMETER ShowOutput
    Display the output to console (default: true)
.EXAMPLE
    Invoke-TDScript -Script 'print("Hello from TouchDesigner")'
.EXAMPLE
    $result = Invoke-TDScript -Script 'op("/project1").children' -ShowOutput $false
#>
function Invoke-TDScript {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Script,
        
        [Parameter(Mandatory=$false)]
        [bool]$ShowOutput = $true
    )
    
    try {
        # Create JSON body with 'script' parameter (NOT 'code')
        $body = @{
            script = $Script
        } | ConvertTo-Json -Depth 10
        
        # Send HTTP POST request
        $response = Invoke-WebRequest -Uri $global:TD_ENDPOINT `
            -Method POST `
            -Body $body `
            -ContentType 'application/json' `
            -UseBasicParsing `
            -TimeoutSec ($global:TD_TIMEOUT / 1000)
        
        # Parse JSON response
        $json = $response.Content | ConvertFrom-Json
        
        # Display output if requested
        if ($ShowOutput -and $json.output) {
            Write-Host $json.output
        }
        
        # Check for errors
        if ($json.errors -and $json.errors.Count -gt 0) {
            Write-Host "Errors:" -ForegroundColor Red
            $json.errors | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        }
        
        return $json
    }
    catch {
        Write-Host "HTTP Request Failed: $_" -ForegroundColor Red
        Write-Host "Make sure TouchDesigner is running and Web Server DAT is on port 9980" -ForegroundColor Yellow
        return $null
    }
}

<#
.SYNOPSIS
    Test connection to TouchDesigner
.EXAMPLE
    Test-TDConnection
#>
function Test-TDConnection {
    Write-Host "Testing TouchDesigner connection..." -ForegroundColor Cyan
    $result = Invoke-TDScript -Script 'print("Connection successful!")'
    
    if ($result) {
        Write-Host "✓ TouchDesigner is connected and responding" -ForegroundColor Green
        return $true
    } else {
        Write-Host "✗ Cannot connect to TouchDesigner" -ForegroundColor Red
        return $false
    }
}

<#
.SYNOPSIS
    Load configuration from touchdesigner.config.json
.EXAMPLE
    $config = Get-TDConfig
#>
function Get-TDConfig {
    $configPath = Join-Path $PSScriptRoot "..\..\touchdesigner.config.json"
    
    if (Test-Path $configPath) {
        $config = Get-Content $configPath | ConvertFrom-Json
        $global:TD_ENDPOINT = $config.api.endpoint
        $global:TD_TIMEOUT = $config.api.timeout
        return $config
    } else {
        Write-Host "Warning: touchdesigner.config.json not found" -ForegroundColor Yellow
        return $null
    }
}

# Export functions
Export-ModuleMember -Function Invoke-TDScript, Test-TDConnection, Get-TDConfig
