out vec4 fragColor;
uniform float uSentinel;
void main(){
    vec2 res = uTD2DInfos[0].res.zw;          // (w,h)
    ivec2 p = ivec2(vUV.st * res);
    float fg = texelFetch(sTD2DInputs[0], p, 0).r;
    if (fg > 0.5) {
        fragColor = TDOutputSwizzle(vec4(float(p.x), float(p.y), 1.0, 1.0));
    } else {
        fragColor = TDOutputSwizzle(vec4(uSentinel, uSentinel, 0.0, 1.0));
    }
}
