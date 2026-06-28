out vec4 fragColor;
uniform float uMatchRadius;   // normalized centroid distance
uniform float uFrameSalt;     // changes per frame; offsets newborn ids
void main(){
    vec2 res = uTD2DInfos[0].res.zw;
    ivec2 p = ivec2(vUV.st * res);
    vec4 cur = texelFetch(sTD2DInputs[0], p, 0);   // (cx,cy,area,valid)
    if (cur.a < 0.5) { fragColor = TDOutputSwizzle(vec4(0.0)); return; }
    int W = int(res.x), H = int(res.y);
    float best = uMatchRadius * uMatchRadius;
    float bestId = 0.0; bool found = false;
    for (int y = 0; y < H; ++y) {
        for (int x = 0; x < W; ++x) {
            vec4 prev = texelFetch(sTD2DInputs[1], ivec2(x,y), 0);  // (id,cx,cy,valid)
            if (prev.a < 0.5) continue;
            vec2 d = prev.gb - cur.rg;             // prev centroid (g,b) - cur centroid (r,g)
            float dd = dot(d, d);
            if (dd < best) { best = dd; bestId = prev.r; found = true; }
        }
    }
    float id = found ? bestId : (float(p.y) * res.x + float(p.x) + uFrameSalt);
    fragColor = TDOutputSwizzle(vec4(id, cur.r, cur.g, cur.b > 0.0 ? 1.0 : 1.0));
    // store: (id, cx, cy, valid=1); area carried separately via glsl_centroid for out_blobs
}
