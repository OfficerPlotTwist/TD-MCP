// post-cartoon-i — TouchDesigner GLSL TOP
// Quantized luminance cel-shading + angled hatching + normal-edge outlines
//
// Inputs: [0]=color  [1]=normal
// (paper grain and FBM noise are procedural)
// Uniforms: inkColor(vec3 0-255) scale thickness noisiness angle

#define colorTexture  sTD2DInputs[0]
#define normalTexture sTD2DInputs[1]

uniform vec3  inkColor;
uniform float scale;
uniform float thickness;
uniform float noisiness;
uniform float angle;

out vec4 fragColor;

// --- procedural noise ---
float _h(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453123); }
float _vn(vec2 p) {
    vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
    return mix(mix(_h(i),_h(i+vec2(1,0)),f.x),mix(_h(i+vec2(0,1)),_h(i+vec2(1,1)),f.x),f.y);
}
float fbm3(vec3 v) { return (_vn(v.xy)+_vn(v.xy*2.)*.5+_vn(v.xy*4.)*.25)/1.75; }
float simplex(vec3 v) { return _vn(v.xy/32.)*2.-1.; }
vec3 paper(vec2 st, vec2 sz) { return vec3(_vn(st*sz*.5)*0.12+0.88); }

// --- shared helpers ---
vec4 sobel(in sampler2D src, in vec2 uv, in vec2 res, in float w) {
    float x=w/res.x, y=w/res.y;
    vec4 h=vec4(0.), v=vec4(0.);
    h-=texture(src,vec2(uv.x-x,uv.y-y)); h-=texture(src,vec2(uv.x-x,uv.y))*2.; h-=texture(src,vec2(uv.x-x,uv.y+y));
    h+=texture(src,vec2(uv.x+x,uv.y-y)); h+=texture(src,vec2(uv.x+x,uv.y))*2.; h+=texture(src,vec2(uv.x+x,uv.y+y));
    v-=texture(src,vec2(uv.x-x,uv.y-y)); v-=texture(src,vec2(uv.x,uv.y-y))*2.; v-=texture(src,vec2(uv.x+x,uv.y-y));
    v+=texture(src,vec2(uv.x-x,uv.y+y)); v+=texture(src,vec2(uv.x,uv.y+y))*2.; v+=texture(src,vec2(uv.x+x,uv.y+y));
    return sqrt(h*h+v*v);
}
float luma(vec3 c) { return dot(c,vec3(0.299,0.587,0.114)); }
float aastep(float t,float val) {
    float afw=length(vec2(dFdx(val),dFdy(val)))*0.70710678;
    return smoothstep(t-afw,t+afw,val);
}
vec3 blendDarken(vec3 a,vec3 b,float op) { return min(a,b)*op+a*(1.-op); }

#define TAU   6.28318530718
#define LEVS  10
#define fLEV  10.0

float sampleStep(in sampler2D src, in vec2 uv, in float level) {
    return round(luma(texture(src,uv).rgb)*fLEV)/fLEV > level ? 1. : 0.;
}
float findBorder(in sampler2D src, in vec2 uv, in vec2 res, in float level) {
    float x=thickness/res.x, y=thickness/res.y, h=0., v=0.;
    h-=sampleStep(src,vec2(uv.x-x,uv.y-y),level); h-=sampleStep(src,vec2(uv.x-x,uv.y),level)*2.; h-=sampleStep(src,vec2(uv.x-x,uv.y+y),level);
    h+=sampleStep(src,vec2(uv.x+x,uv.y-y),level); h+=sampleStep(src,vec2(uv.x+x,uv.y),level)*2.; h+=sampleStep(src,vec2(uv.x+x,uv.y+y),level);
    v-=sampleStep(src,vec2(uv.x-x,uv.y-y),level); v-=sampleStep(src,vec2(uv.x,uv.y-y),level)*2.; v-=sampleStep(src,vec2(uv.x+x,uv.y-y),level);
    v+=sampleStep(src,vec2(uv.x-x,uv.y+y),level); v+=sampleStep(src,vec2(uv.x,uv.y+y),level)*2.; v+=sampleStep(src,vec2(uv.x+x,uv.y+y),level);
    return sqrt(h*h+v*v);
}

void main() {
    vec2 st=vUV.st, size=vec2(textureSize(colorTexture,0));
    float c=0., col=0., hatch=1.;
    for(int i=0;i<LEVS;i++){
        float f=float(i)/fLEV, ss=scale*mix(1.,4.,f);
        vec2 off=noisiness*vec2(fbm3(vec3(ss*st,1.)),fbm3(vec3(ss*st.yx,1.)));
        vec2 uv=st+off;
        float l=round(luma(texture(colorTexture,uv).rgb)*fLEV)/fLEV;
        c+=clamp(findBorder(colorTexture,uv,size,f)-5.*l,0.,1.);
        col+=l/fLEV;
        if(l<.5){
            float a=angle+mix(0.,3.2*TAU,l);
            vec2 ruv=mat2(cos(a),-sin(a),sin(a),cos(a))*uv;
            float thr=mix(50.,400.,2.*l);
            hatch*=abs(mod(ruv.y*size.y+float(i)*thr/fLEV,thr))<1.?0.:1.;
        }
    }
    vec2 off=noisiness*vec2(fbm3(vec3(scale*st,1.)),fbm3(vec3(scale*st.yx,1.)));
    c+=aastep(.5,length(sobel(normalTexture,st+off,size,3.*thickness)));
    col=clamp(col*2.,0.,1.); hatch=1.-hatch;
    vec3 ink=inkColor/255.;
    fragColor.rgb=blendDarken(paper(st,size),ink,1.-col);
    fragColor.rgb=blendDarken(fragColor.rgb,ink,c);
    fragColor.rgb=blendDarken(fragColor.rgb,ink,hatch);
    fragColor.a=1.;
}
