out vec4 fragColor;
uniform float uShow;
void main(){
    vec2 uv = vUV.st;
    vec4 src = texture(sTD2DInputs[0], uv);
    if (uShow < 0.5) { fragColor = TDOutputSwizzle(src); return; }
    vec4 lab = texture(sTD2DInputs[1], uv);          // upscaled label colors
    float m = max(max(lab.r, lab.g), lab.b);         // labeled where any channel lit
    vec3 outc = mix(src.rgb, lab.rgb, step(0.01, m) * 0.6);
    fragColor = TDOutputSwizzle(vec4(outc, 1.0));
}
