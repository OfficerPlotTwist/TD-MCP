out vec4 fragColor;
uniform float uMinArea;
void main(){
    vec2 res = uTD2DInfos[0].res.zw;
    ivec2 p = ivec2(vUV.st * res);
    vec4 acc = texelFetch(sTD2DInputs[0], p, 0);   // (sumx, sumy, count, -)
    float n = acc.b;
    if (n < uMinArea) { fragColor = TDOutputSwizzle(vec4(0.0)); return; }
    vec2 cpx = acc.rg / n;                          // mean pixel coord
    vec2 cnorm = cpx / res;                         // normalize 0..1
    fragColor = TDOutputSwizzle(vec4(cnorm.x, cnorm.y, n, 1.0));
}
