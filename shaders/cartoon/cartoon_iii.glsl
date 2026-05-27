// post-cartoon-iii — TouchDesigner GLSL TOP
// Luminance-threshold hatching (dark/mid) + dot-screen highlights + edge boost
//
// Inputs: [0]=color  [1]=normal
// Uniforms: inkColor(vec3 0-255) scale thickness contour boost dark mid light

#define colorTexture  sTD2DInputs[0]
#define normalTexture sTD2DInputs[1]

uniform vec3  inkColor;
uniform float scale;
uniform float thickness;
uniform float contour;
uniform float boost;
uniform float dark;
uniform float mid;
uniform float light;

out vec4 fragColor;

// --- procedural noise + paper ---
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

vec2 rot(vec2 uv,float deg) {
    float a=deg*6.28318530718/360.;
    return mat2(cos(a),-sin(a),sin(a),cos(a))*uv;
}
float lines(float l,vec2 uv,vec2 res,float thick) {
    uv*=res;
    float c=.5+.5*sin(uv.x*.5), f=(c+thick)*l;
    float e=length(vec2(dFdx(uv.x),dFdy(uv.y)));
    return smoothstep(.5-e,.5+e,f);
}

void main() {
    vec2 st=vUV.st, size=vec2(textureSize(colorTexture,0));
    vec4 color=texture(colorTexture,st);
    float nEdge=1.-length(sobel(normalTexture,st,size,contour));
    nEdge=smoothstep(.5-thickness,.5+thickness,nEdge);
    color.rgb=boost*blendDarken(color.rgb,vec3(0.),.5-nEdge);
    float l=luma(color.rgb);
    vec3 rgb=color.rgb;
    if(l<dark) {
        float k=lines(l/dark,rot(scale*st,45.),size,thickness);
        rgb=mix(rgb,mix(rgb,inkColor/255.,.5),1.-k);
    }
    if(l<mid) {
        float k=lines(l/mid,rot(scale*st,15.),size,thickness);
        rgb=mix(rgb,mix(rgb,inkColor/255.,.5),1.-k);
    }
    if(l>light) {
        mat2 km=mat2(0.707,0.707,-0.707,0.707);
        vec2 Kst=0.05*scale*km*(st*size);
        vec2 Kuv=thickness*(2.*fract(Kst)-1.);
        float k=step(0.,sqrt(l-light)-length(Kuv));
        rgb=blendScreen(rgb,vec3(1.),k);
    }
    fragColor.rgb=blendDarken(paper(st,size),rgb,1.);
    fragColor.a=1.;
}
