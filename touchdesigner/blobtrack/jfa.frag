out vec4 fragColor;
uniform float uStep;
void main(){
    vec2 res = uTD2DInfos[0].res.zw;
    ivec2 p = ivec2(vUV.st * res);
    vec4 self = texelFetch(sTD2DInputs[0], p, 0);
    if (self.b < 0.5) { fragColor = TDOutputSwizzle(self); return; }  // background frozen
    vec2 bestRoot = self.rg;
    float bestKey = bestRoot.y * res.x + bestRoot.x;
    int s = int(uStep);
    int W = int(res.x), H = int(res.y);
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            if (dx == 0 && dy == 0) continue;
            ivec2 q = p + ivec2(dx, dy) * s;
            if (q.x < 0 || q.y < 0 || q.x >= W || q.y >= H) continue;
            vec4 nb = texelFetch(sTD2DInputs[0], q, 0);
            if (nb.b < 0.5) continue;                 // only foreground propagates
            float key = nb.g * res.x + nb.r;
            if (key < bestKey) { bestKey = key; bestRoot = nb.rg; }
        }
    }
    fragColor = TDOutputSwizzle(vec4(bestRoot, 1.0, 1.0));
}
