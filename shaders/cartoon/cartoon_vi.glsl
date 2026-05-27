// post-cartoon-vi — TouchDesigner GLSL TOP
// Quantized cel-shading + dot-screen highlights screen-blended on top
//
// Inputs: [0]=color  [1]=normal
// Uniforms: inkColor(vec3 0-255) scale levels thickness contour minLuma maxLuma
//           minLight lightBoost expLight

#define colorTexture  sTD2DInputs[0]
#define normalTexture sTD2DInputs[1]

uniform vec3  inkColor;
uniform float scale;
uniform float levels;
uniform float thickness;
uniform float contour;
uniform float minLuma;
uniform float maxLuma;
uniform float minLight;
uniform float lightBoost;
uniform float expLight;

out vec4 fragColor;

// --- procedural paper grain ---
float _h(vec2 p) { return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453123); }
float _vn(vec2 p) {
    vec2 i=floor(p),f=fract(p); f=f*f*(3.-2.*f);
    return mix(mix(_h(i),_h(i+vec2(1,0)),f.x),mix(_h(i+vec2(0,1)),_h(i+vec2(1,1)),f.x),f.y);
}
vec3 paper(vec2 st,vec2 sz) { return vec3(_vn(st*sz*.5)*0.12+0.88); }

// --- helpers ---
vec4 sobel(in sampler2D src,in vec2 uv,in vec2 res,in float w) {
    float x=w/res.x, y=w/res.y;
    vec4 h=vec4(0.),v=vec4(0.);
    h-=texture(src,vec2(uv.x-x,uv.y-y)); h-=texture(src,vec2(uv.x-x,uv.y))*2.; h-=texture(src,vec2(uv.x-x,uv.y+y));
    h+=texture(src,vec2(uv.x+x,uv.y-y)); h+=texture(src,vec2(uv.x+x,uv.y))*2.; h+=texture(src,vec2(uv.x+x,uv.y+y));
    v-=texture(src,vec2(uv.x-x,uv.y-y)); v-=texture(src,vec2(uv.x,uv.y-y))*2.; v-=texture(src,vec2(uv.x+x,uv.y-y));
    v+=texture(src,vec2(uv.x-x,uv.y+y)); v+=texture(src,vec2(uv.x,uv.y+y))*2.; v+=texture(src,vec2(uv.x+x,uv.y+y));
    return sqrt(h*h+v*v);
}
float luma(vec3 c) { return dot(c,vec3(0.299,0.587,0.114)); }
vec3 blendDarken(vec3 a,vec3 b,float op) { return min(a,b)*op+a*(1.-op); }
vec3 blendScreen(vec3 a,vec3 b,float op) { return (1.-(1.-a)*(1.-b))*op+a*(1.-op); }

void main() {
    vec2 st=vUV.st, size=vec2(textureSize(colorTexture,0));
    vec4 color=texture(colorTexture,st);
    float nEdge=1.-length(sobel(normalTexture,st,size,contour));
    float l0=luma(color.rgb);
    float l=smoothstep(minLuma,maxLuma,l0);
    float shadeCol=round(l*levels)/levels*nEdge;
    vec3 rgb=mix(vec3(1.),inkColor/255.,1.-shadeCol);
    mat2 k=mat2(0.707,0.707,-0.707,0.707);
    vec2 Kst=0.05*scale*k*(st*size);
    vec2 Kuv=2.*fract(Kst)-1.;
    float dot=step(0.,minLight+expLight*exp(l)+sqrt((l+minLight)*thickness)-length(Kuv));
    vec3 dots=lightBoost*(l+minLight)*vec3(dot);
    fragColor.rgb=blendDarken(paper(st,size),rgb,1.);
    fragColor.rgb=blendScreen(fragColor.rgb,dots,1.);
    fragColor.a=1.;
}
