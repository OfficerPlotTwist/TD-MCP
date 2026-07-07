// morph.frag — silhouette frame-difference for the rest-trigger morph heuristic.
// sTD2DInputs[0] = current mask (R=1 foreground), sTD2DInputs[1] = previous-frame mask.
// Output R = 1.0 where the silhouette flipped this frame, else 0.0.
out vec4 fragColor;

void main()
{
    float a = texture(sTD2DInputs[0], vUV.st).r;   // mask_t
    float b = texture(sTD2DInputs[1], vUV.st).r;   // mask_{t-1}
    float d = abs(a - b);
    fragColor = TDOutputSwizzle(vec4(d, d, d, 1.0));
}
