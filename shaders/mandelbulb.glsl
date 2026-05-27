// Mandelbulb Fractal — Raymarched SDF
// 3D fractal rendered via sphere tracing with orbit-trap coloring.
// Palette texture on sTD2DInputs[0], environment map (equirectangular) on sTD2DInputs[1]
// TouchDesigner GLSL TOP — Pixel Shader — GLSL 4.60
//
// Rebuilt from "TouchDesigner GLSL Shaders for Generative Visuals"
// (The Interactive & Immersive HQ). Uniform set + values matched to the video.

// ---- Uniforms (set on the GLSL TOP "Vectors" page) ----
uniform float uTime;        // animation time (Constant 'time' -> Speed CHOP)
uniform vec2  uResolution;  // 2048 x 2048
uniform float uPower;       // fractal power, audio-driven ~2..8 (default 2)
uniform float uCamSpeed;    // orbit speed (0.15)
uniform float uAOStrength;  // ambient occlusion strength (0.04)
uniform float uFogDensity;  // depth fog falloff (0.02)
uniform float uEnvStrength; // environment map contribution (1.0)
uniform float uCamDist;     // camera distance / zoom (5.0)

// ---- Compile-time constants (#define, not uniforms) ----
#define MAX_STEPS   128
#define MAX_DIST    10.0
#define SURF_DIST   0.001
#define ITERATIONS  12
#define BAILOUT     2.0
#define CAM_HEIGHT  0.3
#define AO_STEPS    5
#define SHADOW_SOFT 16.0
#define BG_COLOR    vec3(0.02, 0.02, 0.04)
#define AA_SAMPLES  4
#define PI          3.14159265359

// Mandelbulb distance estimator with orbit trap (min radius over the orbit).
float mandelbulbDE(vec3 pos, out float trap) {
    vec3 z = pos;
    float dr = 1.0;
    float r  = 0.0;
    trap = 1e10;
    for (int i = 0; i < ITERATIONS; i++) {
        r = length(z);
        if (r > BAILOUT) break;
        float theta = acos(clamp(z.z / r, -1.0, 1.0));
        float phi   = atan(z.y, z.x);
        dr = pow(r, uPower - 1.0) * uPower * dr + 1.0;
        float zr = pow(r, uPower);
        theta *= uPower;
        phi   *= uPower;
        z = zr * vec3(sin(theta) * cos(phi),
                      sin(theta) * sin(phi),
                      cos(theta));
        z += pos;
        trap = min(trap, r);
    }
    return 0.5 * log(r) * r / dr;
}

float mapD(vec3 p) { float t; return mandelbulbDE(p, t); }

vec3 calcNormal(vec3 p) {
    vec2 e = vec2(1.0, -1.0) * 0.0005;
    return normalize(
        e.xyy * mapD(p + e.xyy) +
        e.yyx * mapD(p + e.yyx) +
        e.yxy * mapD(p + e.yxy) +
        e.xxx * mapD(p + e.xxx));
}

float calcAO(vec3 p, vec3 n) {
    float occ = 0.0;
    float sca = 1.0;
    for (int i = 0; i < AO_STEPS; i++) {
        float h = 0.01 + 0.12 * float(i) / float(AO_STEPS);
        float d = mapD(p + n * h);
        occ += (h - d) * sca;
        sca *= 0.95;
    }
    return clamp(1.0 - uAOStrength * occ * 8.0, 0.0, 1.0);
}

float softShadow(vec3 ro, vec3 rd, float mint, float maxt) {
    float res = 1.0;
    float t = mint;
    for (int i = 0; i < 48; i++) {
        if (t > maxt) break;
        float h = mapD(ro + rd * t);
        if (h < SURF_DIST) return 0.0;
        res = min(res, SHADOW_SOFT * h / t);
        t += clamp(h, 0.01, 0.3);
    }
    return clamp(res, 0.0, 1.0);
}

// Equirectangular environment map sample from sTD2DInputs[1].
vec3 sampleEnvMap(vec3 dir) {
    float u = atan(dir.z, dir.x) / (2.0 * PI) + 0.5;
    float v = acos(clamp(dir.y, -1.0, 1.0)) / PI;
    return texture(sTD2DInputs[1], vec2(u, v)).rgb;
}

// Palette from sTD2DInputs[0]; orbit-trap value (0..1) indexes horizontally.
vec3 palette(float t) {
    return texture(sTD2DInputs[0], vec2(clamp(t, 0.0, 1.0), 0.5)).rgb;
}

vec3 render(vec2 uv) {
    // Orbiting camera.
    float a   = uTime * uCamSpeed;
    vec3  ro  = vec3(sin(a) * uCamDist, CAM_HEIGHT, cos(a) * uCamDist);
    vec3  ta  = vec3(0.0);
    vec3  fwd = normalize(ta - ro);
    vec3  rgt = normalize(cross(vec3(0.0, 1.0, 0.0), fwd));
    vec3  up  = cross(fwd, rgt);
    vec3  rd  = normalize(uv.x * rgt + uv.y * up + 1.5 * fwd);

    // Sphere-trace the fractal.
    float t    = 0.0;
    float trap = 1e10;
    bool  hit  = false;
    for (int i = 0; i < MAX_STEPS; i++) {
        vec3  p = ro + rd * t;
        float tr;
        float d = mandelbulbDE(p, tr);
        if (d < SURF_DIST) { hit = true; trap = tr; break; }
        t += d;
        if (t > MAX_DIST) break;
    }

    vec3 col;
    if (hit) {
        vec3  p   = ro + rd * t;
        vec3  n   = calcNormal(p);
        float ao  = calcAO(p, n);
        vec3  lig = normalize(vec3(0.8, 0.7, -0.6));
        float dif = clamp(dot(n, lig), 0.0, 1.0);
        float sh  = softShadow(p + n * SURF_DIST * 2.0, lig, 0.02, 3.0);

        vec3 base = palette(trap);                 // orbit-trap palette
        col = base * (0.2 + 0.8 * dif * sh) * ao;

        vec3  refl    = reflect(rd, n);
        vec3  envRefl = sampleEnvMap(refl) * uEnvStrength;
        float fresnel = pow(1.0 - clamp(dot(n, -rd), 0.0, 1.0), 3.0);
        col = mix(col, envRefl, fresnel * 0.4);

        vec3  bgEnv = sampleEnvMap(rd) * uEnvStrength;
        float fog   = exp(-t * t * uFogDensity);
        col = mix(bgEnv * 0.5 + BG_COLOR, col, fog);
    } else {
        col = sampleEnvMap(rd) * uEnvStrength * 0.5 + BG_COLOR;
    }
    return col;
}

out vec4 fragColor;

void main() {
    vec3 col = vec3(0.0);
    // 2x2 supersampling anti-aliasing.
    for (int m = 0; m < AA_SAMPLES; m++) {
        vec2 off = vec2(float(m % 2), float(m / 2)) * 0.5 - 0.25;
        vec2 uv  = (2.0 * (gl_FragCoord.xy + off) - uResolution) / uResolution.y;
        col += render(uv);
    }
    col /= float(AA_SAMPLES);

    // Tone map + gamma.
    col = col / (1.0 + col);
    col = pow(col, vec3(0.4545));
    fragColor = TDOutputSwizzle(vec4(col, 1.0));
}
