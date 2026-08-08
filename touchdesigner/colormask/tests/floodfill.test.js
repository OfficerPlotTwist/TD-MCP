const test = require("node:test");
const assert = require("node:assert");
const { colorDist, floodFill, byColorMask } =
  require("../webapp/static/floodfill.js");

// 4x2 image: left 2x2 red block, right 2x2 blue block
//   R R B B
//   R R B B
function img() {
  const w = 4, h = 2;
  const d = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      if (x < 2) { d[i] = 255; d[i + 2] = 0; }
      else { d[i] = 0; d[i + 2] = 255; }
      d[i + 1] = 0; d[i + 3] = 255;
    }
  }
  return { d, w, h };
}

test("colorDist normalized euclidean", () => {
  assert.strictEqual(colorDist(255, 0, 0, 255, 0, 0), 0);
  assert.ok(Math.abs(colorDist(255, 0, 0, 0, 0, 0) - 1.0) < 1e-9);
  assert.ok(Math.abs(colorDist(255, 255, 255, 0, 0, 0) - Math.sqrt(3)) < 1e-9);
});

test("floodFill selects connected same-color region only", () => {
  const { d, w, h } = img();
  const m = floodFill(d, w, h, 0, 0, 0.1);
  assert.deepStrictEqual(Array.from(m),
    [255, 255, 0, 0,
     255, 255, 0, 0]);
});

test("floodFill with huge tol takes everything connected", () => {
  const { d, w, h } = img();
  const m = floodFill(d, w, h, 0, 0, 2.0);
  assert.ok(Array.from(m).every(v => v === 255));
});

test("byColorMask selects disconnected matches", () => {
  const w = 4, h = 1;                      // R B R B
  const d = new Uint8ClampedArray(w * h * 4);
  for (let x = 0; x < w; x++) {
    const i = x * 4;
    if (x % 2 === 0) d[i] = 255; else d[i + 2] = 255;
    d[i + 3] = 255;
  }
  const m = byColorMask(d, w, h, [255, 0, 0], 0.1);
  assert.deepStrictEqual(Array.from(m), [255, 0, 255, 0]);
});
