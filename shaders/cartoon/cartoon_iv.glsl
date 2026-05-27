// post-cartoon-iv — TouchDesigner GLSL TOP
// Full CMYK fill + shade (derived from color) + dark/bright ink hatching + dot patterns
//
// Inputs: [0]=color  [1]=normal  [2]=component(CMYK)
// Uniforms: darkInk brightInk scale thickness noisiness angle contour border fill stroke
//           darkIntensity brightIntensity

#define colorTexture     sTD2DInputs[0]
#define normalTexture    sTD2DInputs[1]
#define componentTexture sTD2DInputs[2]

uniform vec3  darkInk;
uniform vec3  brightInk;
uniform float scale;
uniform float thickness;
uniform float noisiness;
uniform float angle;
uniform float contour;
uniform float border;
uniform float fill;
uniform float stroke;
uniform float darkIntensity;
uniform float brightIntensity;

out vec4 fragColor;

// --- procedural noise + paper ---
float _h(vec2 p) { return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453123); }
float _vn(vec2 p) {
    vec2 i=floor(p),f=fract(p); f=f*f*(3.-2.*f);
    return mix(mix(_h(i),_h(i+vec2(1,0)),f.x),mix(_h(i+vec2(0,1)),_h(i+vec2(1,1)),f.x),f.y);
}
float fbm3(vec3 v) { return (_vn(v.xy)+_vn(v.xy*2.)*.5+_vn(v.xy*4.)*.25)/1.75; }
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
float luma(vec4 c) { return dot(c.rgb,vec3(0.299,0.587,0.114)); }
float aastep(float t,float val) {
    float afw=length(vec2(dFdx(val),dFdy(val)))*0.70710678;
    return smoothstep(t-afw,t+afw,val);
}
vec3 blendDarken(vec3 a,vec3 b,float op) { return min(a,b)*op+a*(1.-op); }
vec3 blendScreen(vec3 a,vec3 b,float op) { return (1.-(1.-a)*(1.-b))*op+a*(1.-op); }
vec3 CMYKtoRGB(vec4 cmyk) {
    float invK=1.-cmyk.w;
    return clamp(vec3(1.-min(1.,cmyk.x*invK+cmyk.w),1.-min(1.,cmyk.y*invK+cmyk.w),1.-min(1.,cmyk.z*invK+cmyk.w)),0.,1.);
}

#define TAU  6.28318530718
#define LEVS 5
#define fLEV 5.0

vec4 sampleStep4(in vec2 uv,in float level) {
    vec4 l=round(texture(componentTexture,uv)*fLEV)/fLEV;
    return vec4(l.x>level?1.:0.,l.y>level?1.:0.,l.z>level?1.:0.,l.w>level?1.:0.);
}
vec4 findBorder4(in vec2 uv,in vec2 res,in float level) {
    float x=thickness/res.x, y=thickness/res.y;
    vec4 h=vec4(0.),v=vec4(0.);
    h-=sampleStep4(vec2(uv.x-x,uv.y-y),level); h-=sampleStep4(vec2(uv.x-x,uv.y),level)*2.; h-=sampleStep4(vec2(uv.x-x,uv.y+y),level);
    h+=sampleStep4(vec2(uv.x+x,uv.y-y),level); h+=sampleStep4(vec2(uv.x+x,uv.y),level)*2.; h+=sampleStep4(vec2(uv.x+x,uv.y+y),level);
    v-=sampleStep4(vec2(uv.x-x,uv.y-y),level); v-=sampleStep4(vec2(uv.x,uv.y-y),level)*2.; v-=sampleStep4(vec2(uv.x+x,uv.y-y),level);
    v+=sampleStep4(vec2(uv.x-x,uv.y+y),level); v+=sampleStep4(vec2(uv.x,uv.y+y),level)*2.; v+=sampleStep4(vec2(uv.x+x,uv.y+y),level);
    return sqrt(h*h+v*v);
}
float doHatch(in float l,in float r,in float a,in vec2 uv) {
    if(l>r) return 1.;
    float ra=angle+a+mix(0.,3.2*TAU,l);
    uv=mat2(cos(ra),-sin(ra),sin(ra),cos(ra))*uv;
    float thr=mix(2.,40.,l);
    return abs(mod(uv.y+r*thr,thr))<thickness?0.:1.;
}
float lines(float l,vec2 fragCoord,vec2 res,float thick) {
    vec2 uv=fragCoord*res;
    float c=.5+.5*sin(uv.x*.5), f=(c+thick)*l;
    float e=length(vec2(dFdx(fragCoord.x),dFdy(fragCoord.y)));
    return smoothstep(.5-e,.5+e,f);
}

void main() {
    vec2 st=vUV.st, size=vec2(textureSize(colorTexture,0));
    vec4 col=vec4(0.), borders=vec4(0.);
    for(int i=0;i<LEVS;i++){
        float f=float(i)/fLEV, ss=scale*mix(1.,4.,f);
        vec2 off=noisiness*vec2(fbm3(vec3(ss*st,1.)),fbm3(vec3(ss*st.yx,1.)));
        vec2 uv=st+off;
        borders+=findBorder4(uv,size,f);
        col+=sampleStep4(uv,f)/fLEV;
    }
    // shade derived from color (replaces separate shadeTexture)
    float shadeCol=0., shadeBorder=0.;
    for(int i=0;i<3;i++){
        float f=float(i)/3., ss=scale*mix(1.,4.,f);
        vec2 off=noisiness*vec2(fbm3(vec3(ss*st,1.)),fbm3(vec3(ss*st.yx,1.)));
        vec2 uv=st+off;
        float bv=0.,h=0.,v=0.;
        float x=thickness/size.x, y=thickness/size.y;
        float lc=round(luma(texture(colorTexture,uv).rgb)*fLEV)/fLEV;
        // scalar border
        float[6] ns; ns[0]=luma(texture(colorTexture,vec2(uv.x-x,uv.y-y)).rgb); ns[1]=luma(texture(colorTexture,vec2(uv.x-x,uv.y)).rgb); ns[2]=luma(texture(colorTexture,vec2(uv.x-x,uv.y+y)).rgb); ns[3]=luma(texture(colorTexture,vec2(uv.x+x,uv.y-y)).rgb); ns[4]=luma(texture(colorTexture,vec2(uv.x+x,uv.y)).rgb); ns[5]=luma(texture(colorTexture,vec2(uv.x+x,uv.y+y)).rgb);
        float s0=round(ns[0]*fLEV)/fLEV>f?1.:0., s1=round(ns[1]*fLEV)/fLEV>f?1.:0., s2=round(ns[2]*fLEV)/fLEV>f?1.:0.;
        float s3=round(ns[3]*fLEV)/fLEV>f?1.:0., s4=round(ns[4]*fLEV)/fLEV>f?1.:0., s5=round(ns[5]*fLEV)/fLEV>f?1.:0.;
        h=-s0-s1*2.-s2+s3+s4*2.+s5;
        float sv0=round(luma(texture(colorTexture,vec2(uv.x-x,uv.y-y)).rgb)*fLEV)/fLEV>f?1.:0.;
        float sv1=round(luma(texture(colorTexture,vec2(uv.x,uv.y-y)).rgb)*fLEV)/fLEV>f?1.:0.;
        float sv2=round(luma(texture(colorTexture,vec2(uv.x+x,uv.y-y)).rgb)*fLEV)/fLEV>f?1.:0.;
        float sv3=round(luma(texture(colorTexture,vec2(uv.x-x,uv.y+y)).rgb)*fLEV)/fLEV>f?1.:0.;
        float sv4=round(luma(texture(colorTexture,vec2(uv.x,uv.y+y)).rgb)*fLEV)/fLEV>f?1.:0.;
        float sv5=round(luma(texture(colorTexture,vec2(uv.x+x,uv.y+y)).rgb)*fLEV)/fLEV>f?1.:0.;
        v=-sv0-sv1*2.-sv2+sv3+sv4*2.+sv5;
        shadeBorder+=sqrt(h*h+v*v);
        shadeCol+=lc/3.;
    }
    float ss=scale*5.;
    vec2 off=noisiness*vec2(fbm3(vec3(ss*st,1.)),fbm3(vec3(ss*st.yx,1.)));
    vec2 uv=st+off;
    vec4 cc=round((1.-texture(componentTexture,uv))*fLEV)/fLEV;
    vec4 hatch=vec4(doHatch(cc.x,.75,75.,uv*size),doHatch(cc.y,.75,15.,uv*size),doHatch(cc.z,.75,0.,uv*size),doHatch(cc.w,.75,45.,uv*size));
    mat2 r45=mat2(0.707,-0.707,0.707,0.707);
    float shadeL=luma(texture(colorTexture,uv).rgb);
    float shadeHatch=lines(1.5*shadeL,r45*st,size,1.);
    float whiteHatch=lines(shadeL/2.,r45*st,size,1.);
    float nEdge=aastep(.5,length(sobel(normalTexture,uv,size,contour)));
    float k=col.w; col.w=0.;
    vec3 dink=darkInk/255., bink=brightInk/255.;
    fragColor.rgb=blendDarken(paper(st,size),CMYKtoRGB(col),fill);
    fragColor.rgb=blendDarken(fragColor.rgb,dink,fill*k);
    fragColor.rgb=blendDarken(fragColor.rgb,dink,nEdge);
    fragColor.rgb=blendDarken(fragColor.rgb,CMYKtoRGB(borders).rgb,border*.5);
    fragColor.rgb=blendDarken(fragColor.rgb,dink,border*.1*(1.-borders.w));
    fragColor.rgb=blendDarken(fragColor.rgb,CMYKtoRGB(1.-vec4(hatch.xyz,1.)),stroke);
    fragColor.rgb=blendDarken(fragColor.rgb,dink,stroke*(1.-hatch.w));
    float shade=clamp(1.-(shadeCol-shadeBorder*(1.-1.5*shadeCol))-.5,0.,1.);
    fragColor.rgb=blendDarken(fragColor.rgb,dink,border*.25*shade);
    fragColor.rgb=blendDarken(fragColor.rgb,dink,darkIntensity*(1.-shadeHatch));
    fragColor.rgb=blendScreen(fragColor.rgb,bink,brightIntensity*whiteHatch);
    fragColor.a=1.;
}
