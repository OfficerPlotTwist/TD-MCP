# TouchDesigner API Reference

## HTTP API Endpoint

```
POST http://127.0.0.1:9980/execute
Content-Type: application/json
Body: {"script": "python_code"}
```

## Operator Creation

### Basic Pattern
```python
parent = op('/project1')
new_op = parent.create(operatorType, 'operator_name')
```

### Common Operator Types

**TOPs (Texture Operators)**
```python
noise = parent.create(noiseTOP, 'noise1')
glsl = parent.create(glslTOP, 'shader1')
movie = parent.create(moviefileinTOP, 'video1')
render = parent.create(renderTOP, 'render1')
composite = parent.create(compositeTOP, 'comp1')
```

**CHOPs (Channel Operators)**
```python
constant = parent.create(constantCHOP, 'const1')
math = parent.create(mathCHOP, 'math1')
noise = parent.create(noiseCHOP, 'noise1')
timer = parent.create(timerCHOP, 'timer1')
```

**SOPs (Surface Operators)**
```python
box = parent.create(boxSOP, 'box1')
sphere = parent.create(sphereSOP, 'sphere1')
grid = parent.create(gridSOP, 'grid1')
```

**COMPs (Components)**
```python
camera = parent.create(cameraCOMP, 'cam1')
light = parent.create(lightCOMP, 'light1')
geo = parent.create(geometryCOMP, 'geo1')
```

**DATs (Data Operators)**
```python
text = parent.create(textDAT, 'text1')
table = parent.create(tableDAT, 'table1')
script = parent.create(scriptDAT, 'script1')
```

## Operator Positioning

```python
op_node = op('/project1/my_op')
op_node.nodeX = 100  # Horizontal position
op_node.nodeY = 200  # Vertical position
```

## Connecting Operators

### Basic Connection
```python
source = op('/project1/source')
target = op('/project1/target')
target.inputConnectors[0].connect(source)
```

### Multiple Inputs
```python
target.inputConnectors[0].connect(input1)
target.inputConnectors[1].connect(input2)
```

### Disconnect
```python
target.inputConnectors[0].disconnect()
```

## Parameter Access

### Get Parameter Value
```python
value = op_node.par.parametername.eval()
# or
value = op_node.par.parametername
```

### Set Parameter Value
```python
op_node.par.parametername = value
```

### Common Parameters

**Transform Parameters**
```python
op_node.par.tx = 0    # Translate X
op_node.par.ty = 3    # Translate Y
op_node.par.tz = 5    # Translate Z
op_node.par.rx = 0    # Rotate X
op_node.par.ry = 45   # Rotate Y
op_node.par.rz = 0    # Rotate Z
op_node.par.sx = 1    # Scale X
op_node.par.sy = 1    # Scale Y
op_node.par.sz = 1    # Scale Z
```

**Camera Parameters**
```python
cam.par.lookat = 1                    # Enable look at
cam.par.lookatpath = '/project1/target'  # Target path
cam.par.fov = 60                      # Field of view
```

**GLSL Parameters**
```python
glsl.par.pixeldat = text_dat          # Pixel shader DAT
glsl.par.vertexdat = vertex_dat       # Vertex shader DAT
glsl.par.computedat = compute_dat     # Compute shader DAT
```

## Text DAT Operations

### Set Text Content
```python
text_dat = op('/project1/text1')
text_dat.text = 'Your content here'
```

### Multi-line Content
```python
text_dat.text = '''
Line 1
Line 2
Line 3
'''
```

### GLSL Shader Content
```python
text_dat.text = '''
out vec4 fragColor;
void main() {
    fragColor = vec4(1.0, 0.0, 0.0, 1.0);
}
'''
```

## Querying Operators

### Check if Operator Exists
```python
op_node = op('/project1/my_op')
if op_node:
    print(f'Exists: {op_node.path}')
else:
    print('Not found')
```

### List Children
```python
parent = op('/project1')
children = parent.children
for child in children:
    print(f'{child.name} ({child.type})')
```

### Get Operator Type
```python
op_type = op_node.type
print(f'Type: {op_type}')
```

### Get Operator Path
```python
path = op_node.path
print(f'Path: {path}')
```

## Deleting Operators

```python
op_node = op('/project1/my_op')
if op_node:
    op_node.destroy()
    print(f'Deleted: {op_node.name}')
```

## Complete Example

```python
# Create a noise TOP feeding into a GLSL TOP
parent = op('/project1')

# Create noise source
noise = parent.create(noiseTOP, 'noise_source')
noise.nodeX = 0
noise.nodeY = 0

# Create GLSL TOP
glsl = parent.create(glslTOP, 'my_shader')
glsl.nodeX = 300
glsl.nodeY = 0

# Create text DAT for shader code
shader_dat = parent.create(textDAT, 'my_shader_pixel')
shader_dat.nodeX = 300
shader_dat.nodeY = -150

# Set shader code
shader_dat.text = '''
out vec4 fragColor;
void main() {
    vec4 color = texture(sTD2DInputs[0], vUV.st);
    fragColor = TDOutputSwizzle(color * 0.5);
}
'''

# Connect and configure
glsl.inputConnectors[0].connect(noise)
glsl.par.pixeldat = shader_dat

print(f'Created shader network: {noise.path} -> {glsl.path}')
```

## PowerShell Wrapper Example

```powershell
# Source the HTTP functions
. .\scripts\templates\http-request.ps1

# Execute the Python code
$pythonCode = @"
parent = op('/project1')
noise = parent.create(noiseTOP, 'noise1')
print(f'Created: {noise.path}')
"@

$result = Invoke-TDScript -Script $pythonCode
```

## Best Practices

1. **Always print results** - Use `print()` to see output
2. **Check operator exists** - Verify with `if op_node:` before using
3. **Use absolute paths** - `/project1/op_name` not relative paths
4. **Add delays** - Wait 300ms between operations
5. **Handle errors** - Check `$json.errors` in PowerShell
6. **Clean Unicode** - Replace special characters in GLSL files
7. **Use /project1** - Always create in project container, not root
