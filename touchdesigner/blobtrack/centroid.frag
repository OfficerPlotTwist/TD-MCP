out vec4 fragColor;
uniform float uMinArea;
void main(){
    vec2 res = uTD2DInfos[0].res.zw;          // (W, H) of null_label input
    ivec2 rootSlot = ivec2(vUV.st * res);      // this output pixel = candidate root slot

    // Early-out: skip non-root slots (foreground pixel whose root pointer != itself)
    vec4 selfLabel = texelFetch(sTD2DInputs[0], rootSlot, 0);
    if (selfLabel.b < 0.5 ||
        int(round(selfLabel.r)) != rootSlot.x ||
        int(round(selfLabel.g)) != rootSlot.y) {
        fragColor = TDOutputSwizzle(vec4(0.0));
        return;
    }

    float sumX = 0.0, sumY = 0.0, cnt = 0.0;
    int W = int(res.x);
    int H = int(res.y);
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            vec4 lab = texelFetch(sTD2DInputs[0], ivec2(x, y), 0);
            if (lab.b < 0.5) continue;                          // background pixel
            if (int(round(lab.r)) == rootSlot.x &&
                int(round(lab.g)) == rootSlot.y) {              // belongs to our root
                sumX += float(x);
                sumY += float(y);
                cnt  += 1.0;
            }
        }
    }

    if (cnt == 0.0 || cnt < uMinArea) { fragColor = TDOutputSwizzle(vec4(0.0)); return; }
    vec2 cnorm = vec2(sumX, sumY) / (cnt * res);   // normalize pixel mean → [0,1]
    fragColor = TDOutputSwizzle(vec4(cnorm.x, cnorm.y, cnt, 1.0));
}
