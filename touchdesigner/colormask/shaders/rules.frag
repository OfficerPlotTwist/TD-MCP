// Combined color-mask rules. Inputs:
//   0 = source frame, 1 = stencil (R, bottom-up like all TOPs), 2 = rule texture (Nx1)
// Rule texel: rgb = reference color, a = tol + 10*type (type 1 = bycolor), a < 0 = no rules.
// distance() here MUST match colorDist() in webapp/static/floodfill.js.
out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    vec3 src = texture(sTD2DInputs[0], uv).rgb;
    float stencil = texture(sTD2DInputs[1], uv).r;
    int n = textureSize(sTD2DInputs[2], 0).x;
    float m = 0.0;
    for (int i = 0; i < n; i++) {
        vec4 rule = texelFetch(sTD2DInputs[2], ivec2(i, 0), 0);
        if (rule.a < 0.0) continue;
        bool bycolor = rule.a >= 10.0;
        float tol = bycolor ? rule.a - 10.0 : rule.a;
        if (distance(src, rule.rgb) <= tol && (bycolor || stencil > 0.5)) {
            m = 1.0;
        }
    }
    fragColor = vec4(m, m, m, 1.0);
}
