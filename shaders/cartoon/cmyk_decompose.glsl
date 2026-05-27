// CMYK decomposition pre-pass
// Converts input RGB color to CMYK stored as RGBA (C=r, M=g, Y=b, K=a)
// Required for cartoon-ii, cartoon-iv, cartoon-v
//
// Inputs: [0]=color

#define colorTexture sTD2DInputs[0]

out vec4 fragColor;

void main() {
    vec3 rgb = texture(colorTexture, vUV.st).rgb;
    float k = 1. - max(max(rgb.r, rgb.g), rgb.b);
    float denom = max(1. - k, 0.0001);
    fragColor = vec4(
        (1. - rgb.r - k) / denom,
        (1. - rgb.g - k) / denom,
        (1. - rgb.b - k) / denom,
        k
    );
}
