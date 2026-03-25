# Example: GLSL Shader Network

This example creates a noise TOP connected to multiple GLSL shader TOPs.

## What This Creates

- 1 Noise TOP (input source)
- 6 GLSL TOPs (different dithering shaders)
- 6 Text DATs (containing GLSL code)
- All connections configured

## PowerShell Script

```powershell
# Source the HTTP functions
. .\scripts\templates\http-request.ps1

# Load configuration
$config = Get-TDConfig

# GLSL files to process
$glslFiles = @(
    @{name = "atkinson_dither"; file = "atkinson_dither.glsl"},
    @{name = "bayer_dither"; file = "bayer_dither.glsl"},
    @{name = "floyd_steinberg_dither"; file = "floyd_steinberg_dither.glsl"},
    @{name = "random_dither"; file = "random_dither.glsl"},
    @{name = "sierra_dither"; file = "sierra_dither.glsl"},
    @{name = "stucki_dither"; file = "stucki_dither.glsl"}
)

# Step 1: Create noise TOP
Write-Host "Creating noise TOP..."
$noiseScript = @"
parent = op('/project1')
noise = parent.create(noiseTOP, 'noise1')
noise.nodeX = 0
noise.nodeY = 0
print(f'Created: {noise.path}')
"@
Invoke-TDScript -Script $noiseScript
Start-Sleep -Milliseconds 300

# Step 2: Create GLSL TOPs with text DATs
foreach ($item in $glslFiles) {
    $i = [array]::IndexOf($glslFiles, $item)
    $xPos = 200 + ($i * 300)
    
    Write-Host "Creating $($item.name)..."
    
    # Read GLSL file
    $glslContent = Get-Content -Path $item.file -Raw -Encoding UTF8
    
    # Clean Unicode characters
    $glslContent = $glslContent -replace [char]0x2014, '-'
    $glslContent = $glslContent -replace [char]0x2013, '-'
    $glslContent = $glslContent -replace [char]0x201C, '"'
    $glslContent = $glslContent -replace [char]0x201D, '"'
    $glslContent = $glslContent -replace [char]0x2018, "'"
    $glslContent = $glslContent -replace [char]0x2019, "'"
    $glslContent = $glslContent -replace '\\', '\\'
    
    # Create operators
    $glslScript = @"
parent = op('/project1')
glsl = parent.create(glslTOP, '$($item.name)')
text_dat = parent.create(textDAT, '$($item.name)_pixel')
text_dat.text = '''$glslContent'''
glsl.nodeX = $xPos
glsl.nodeY = 0
text_dat.nodeX = $xPos
text_dat.nodeY = -150
noise = op('/project1/noise1')
glsl.inputConnectors[0].connect(noise)
glsl.par.pixeldat = text_dat
print(f'Created: {glsl.path}')
"@
    
    Invoke-TDScript -Script $glslScript
    Start-Sleep -Milliseconds 300
}

Write-Host "`nComplete! Check TouchDesigner /project1"
```

## Result

You'll have a network that looks like:

```
noise1 (noiseTOP)
  ├─> atkinson_dither (glslTOP) ← atkinson_dither_pixel (textDAT)
  ├─> bayer_dither (glslTOP) ← bayer_dither_pixel (textDAT)
  ├─> floyd_steinberg_dither (glslTOP) ← floyd_steinberg_dither_pixel (textDAT)
  ├─> random_dither (glslTOP) ← random_dither_pixel (textDAT)
  ├─> sierra_dither (glslTOP) ← sierra_dither_pixel (textDAT)
  └─> stucki_dither (glslTOP) ← stucki_dither_pixel (textDAT)
```

## Key Learnings

1. **Unicode Handling** - GLSL files often have special characters that must be replaced
2. **Spacing** - 300px horizontal spacing keeps network organized
3. **Naming Convention** - `{shader_name}_pixel` for text DATs
4. **Delays** - 300ms between operations prevents race conditions
5. **Container** - Always use `/project1` as parent
