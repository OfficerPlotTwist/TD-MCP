// Normal-output vertex shader for TouchDesigner GLSL MAT
// Transforms position and passes world-space normal to fragment shader

out vec3 vWorldNormal;

void main() {
    gl_Position = TDWorldToScreen * TDDeform(P);
    vWorldNormal = normalize(mat3(TDObjectToWorld) * N);
}
