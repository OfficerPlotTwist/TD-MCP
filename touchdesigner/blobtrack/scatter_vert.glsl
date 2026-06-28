uniform sampler2D sLabels;   // null_label bound on MAT Samplers page as 'sLabels'
uniform float uRes;          // Procres
out vec4 vScatterColor;
void main(){
    int W = int(uRes);
    ivec2 px = ivec2(uv[0].st * uRes);                  // grid uv 0..1 -> pixel
    vec4 lab = texelFetch(sLabels, px, 0);
    if (lab.b < 0.5) {                                   // background -> offscreen, no contribution
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        vScatterColor = vec4(0.0);
        return;
    }
    int root = int(lab.g) * W + int(lab.r);
    ivec2 slot = ivec2(root % W, root / W);
    vec2 ndc = (vec2(slot) + 0.5) / uRes * 2.0 - 1.0;   // slot center -> clip space
    gl_Position = vec4(ndc, 0.0, 1.0);
    gl_PointSize = 1.0;  // explicit size; wirewidth also set on GLSL MAT
    vScatterColor = vec4(float(px.x), float(px.y), 1.0, 0.0);  // (x, y, count, -)
}
