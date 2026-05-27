// NPR cartoon material — vertex shader

out vec3 vWorldNormal;

void main() {
    gl_Position  = TDWorldToScreen * TDDeform(P);
    vWorldNormal = normalize(TDDeformNorm(N));
}
