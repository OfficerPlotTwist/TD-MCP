// NPR cartoon material — fragment shader
// Implements cel-shading, screen-space hatching, dot highlights, edge detection
// and paper grain directly on SOP geometry. No post-processing pass required.
//
// Uniforms (set via GLSL MAT Vectors page):
//   inkColor   vec3  ink/line colour in 0-255 range  (default: 0,0,0)
//   lightDir   vec3  world-space light direction      (default: 0.5, 1.0, 0.7)
//   scale      float pattern scale                   (default: 1.0)
//   thickness  float line/dot thickness              (default: 1.5)
//   contour    float edge detection strength          (default: 4.0)
//   levels     float cel quantisation levels          (default: 5.0)
//   angle      float hatch angle offset (radians)    (default: 0.0)
//   dark       float luminance threshold for hatching (default: 0.4)
//   light      float luminance threshold for dots     (default: 0.7)

in vec3 vWorldNormal;
in vec3 vWorldPos;
in vec2 vScreenUV;

uniform vec3  inkColor;
uniform vec3  lightDir;
uniform float scale;
uniform float thickness;
uniform float contour;
uniform float levels;
uniform float angle;
uniform float dark;
uniform float light;

out vec4 fragColor;

// --- procedural value noise (paper grain + pattern seed) ---
float _h(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float _vn(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3. - 2. * f);
    return mix(mix(_h(i), _h(i + vec2(1,0)), f.x),
               mix(_h(i + vec2(0,1)), _h(i + vec2(1,1)), f.x), f.y);
}

// --- screen-space edge detection via normal derivatives ---
float edgeDetect(vec3 N, float strength) {
    float ex = length(dFdx(N));
    float ey = length(dFdy(N));
    return clamp(sqrt(ex*ex + ey*ey) * strength, 0., 1.);
}

// --- screen-space hatching ---
float hatch(vec2 sc, float diffuse, float ang, float thick) {
    float a = ang + diffuse * 3.14159265;
    float ca = cos(a), sa = sin(a);
    vec2 ruv = mat2(ca, -sa, sa, ca) * sc;
    float thr = mix(4., 20., clamp(diffuse / max(dark, 0.001), 0., 1.));
    return abs(mod(ruv.y, thr)) < thick ? 0. : 1.;
}

// --- screen-space rotated dot screen ---
float dotScreen(vec2 sc, float diffuse, float thresh, float thick) {
    mat2 km = mat2(0.707, 0.707, -0.707, 0.707);
    vec2 Kst = 0.05 * scale * km * sc;
    vec2 Kuv = 2. * fract(Kst) - 1.;
    return step(0., sqrt(diffuse - thresh) + thick * 0.5 - length(Kuv));
}

void main() {
    vec3 N = normalize(vWorldNormal);

    // --- lighting (simple diffuse) ---
    vec3  ld      = normalize(lightDir);
    float diffuse = clamp(dot(N, ld), 0., 1.);

    // --- cel-shading quantisation ---
    float cel = round(diffuse * levels) / levels;

    // --- base colour: white paper to ink ramp ---
    vec3 ink = inkColor / 255.;
    vec3 rgb = mix(vec3(1.), ink, 1. - cel);

    // --- contour edges via screen-space normal derivatives ---
    float edge = edgeDetect(N, contour);
    rgb = mix(rgb, ink, edge);

    // --- screen-space patterns using gl_FragCoord ---
    vec2 sc = gl_FragCoord.xy * scale;

    // hatching in dark regions
    if (diffuse < dark) {
        float h = hatch(sc, diffuse, angle, thickness);
        rgb = mix(rgb, mix(rgb, ink, 0.8), 1. - h);
    }

    // dot highlights in bright regions
    if (diffuse > light) {
        float d = dotScreen(sc, diffuse, light, thickness);
        rgb = mix(rgb, vec3(1.), d * 0.5);
    }

    // --- paper grain overlay ---
    float grain = _vn(gl_FragCoord.xy * 0.5) * 0.08 + 0.92;
    rgb *= grain;

    fragColor = vec4(rgb, 1.);
}
