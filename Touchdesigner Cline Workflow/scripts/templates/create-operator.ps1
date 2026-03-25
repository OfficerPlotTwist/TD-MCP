# Create Operator Template
# Usage: .\create-operator.ps1 -Type "noiseTOP" -Name "noise1" -Container "/project1"

param(
  [Parameter(Mandatory = $true)]
  [string]$Type,
    
  [Parameter(Mandatory = $true)]
  [string]$Name,
    
  [Parameter(Mandatory = $false)]
  [string]$Container = "/project1",
    
  [Parameter(Mandatory = $false)]
  [int]$X = 0,
    
  [Parameter(Mandatory = $false)]
  [int]$Y = 0
)

# Source the HTTP request functions
. "$PSScriptRoot\http-request.ps1"

Write-Host "`n=== Creating $Type: $Name ===`n" -ForegroundColor Cyan

$script = @"
# Create operator
parent = op('$Container')
if not parent:
    print(f'Error: Container $Container not found')
else:
    new_op = parent.create($Type, '$Name')
    new_op.nodeX = $X
    new_op.nodeY = $Y
    print(f'Created: {new_op.path}')
    print(f'Type: {new_op.type}')
    print(f'Position: ({new_op.nodeX}, {new_op.nodeY})')
"@

$result = Invoke-TDScript -Script $script

if ($result -and -not $result.errors) {
  Write-Host "`n✓ Operator created successfully" -ForegroundColor Green
} else {
  Write-Host "`n✗ Failed to create operator" -ForegroundColor Red
}
