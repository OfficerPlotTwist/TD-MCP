out vec4 fragColor;
void main(){
    vec2 res = uTD2DInfos[0].res.zw;
    ivec2 p = ivec2(vUV.st * res);
    vec4 lab = texelFetch(sTD2DInputs[0], p, 0);   // null_label
    if (lab.b < 0.5) { fragColor = TDOutputSwizzle(vec4(0.0,0.0,0.0,1.0)); return; }
    float key = lab.g * res.x + lab.r;
    vec3 col = vec3(fract(sin(key*12.9898)*43758.5453),
                    fract(sin(key*78.2330)*43758.5453),
                    fract(sin(key*37.7190)*43758.5453));
    fragColor = TDOutputSwizzle(vec4(col, 1.0));
}
