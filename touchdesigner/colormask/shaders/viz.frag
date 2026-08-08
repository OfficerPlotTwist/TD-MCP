// Source tinted magenta where the mask is on. Inputs: 0 = source, 1 = mask.
out vec4 fragColor;
void main() {
    vec3 src = texture(sTD2DInputs[0], vUV.st).rgb;
    float m = texture(sTD2DInputs[1], vUV.st).r;
    fragColor = vec4(mix(src, vec3(1.0, 0.0, 1.0), 0.6 * m), 1.0);
}
