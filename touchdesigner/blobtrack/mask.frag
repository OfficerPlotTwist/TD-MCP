out vec4 fragColor;
uniform float uThreshold;
void main(){
    vec4 c = texture(sTD2DInputs[0], vUV.st);
    float lum = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    float fg = step(uThreshold, lum);
    fragColor = TDOutputSwizzle(vec4(fg, 0.0, 0.0, 1.0));
}
