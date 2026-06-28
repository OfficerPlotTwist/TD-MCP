out vec4 fragColor;
uniform float uTime;     // seconds (absTime.seconds)
void main(){
    vec2 uv = vUV.st;
    vec2 c0 = vec2(0.25, 0.30);
    vec2 c1 = vec2(0.70, 0.65);
    vec2 c2 = vec2(0.50 + 0.15*sin(uTime*0.2*6.2831853), 0.80);
    float r = 0.06;
    float fg = 0.0;
    fg = max(fg, step(distance(uv, c0), r));
    fg = max(fg, step(distance(uv, c1), r));
    fg = max(fg, step(distance(uv, c2), r));
    fragColor = TDOutputSwizzle(vec4(fg, fg, fg, 1.0));
}
