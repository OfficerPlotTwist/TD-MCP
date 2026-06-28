in vec4 vScatterColor;
out vec4 fragColor;
void main(){
    fragColor = TDOutputSwizzle(vScatterColor);   // additive blend accumulates in Render TOP
}
