// Selection math shared by the browser app and node tests.
// colorDist MUST stay identical to distance() in shaders/rules.frag
// (Euclidean distance of normalized 0..1 RGB channels).
"use strict";

function colorDist(r1, g1, b1, r2, g2, b2) {
  const dr = (r1 - r2) / 255, dg = (g1 - g2) / 255, db = (b1 - b2) / 255;
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

// data: RGBA Uint8ClampedArray. Returns Uint8Array (0/255), 4-connectivity
// flood from (sx, sy) over pixels within tol of the seed pixel's color.
function floodFill(data, w, h, sx, sy, tol) {
  const mask = new Uint8Array(w * h);
  if (sx < 0 || sy < 0 || sx >= w || sy >= h) return mask;
  const si = (sy * w + sx) * 4;
  const sr = data[si], sg = data[si + 1], sb = data[si + 2];
  const stack = [sy * w + sx];
  mask[sy * w + sx] = 255;
  while (stack.length) {
    const p = stack.pop();
    const x = p % w, y = (p - x) / w;
    const neighbors = [];
    if (x > 0) neighbors.push(p - 1);
    if (x < w - 1) neighbors.push(p + 1);
    if (y > 0) neighbors.push(p - w);
    if (y < h - 1) neighbors.push(p + w);
    for (const q of neighbors) {
      if (mask[q]) continue;
      const i = q * 4;
      if (colorDist(data[i], data[i + 1], data[i + 2], sr, sg, sb) <= tol) {
        mask[q] = 255;
        stack.push(q);
      }
    }
  }
  return mask;
}

// Frame-wide color test (the "select by color" tool): every pixel within
// tol of seed [r,g,b], disconnected regions included.
function byColorMask(data, w, h, seed, tol) {
  const mask = new Uint8Array(w * h);
  const [sr, sg, sb] = seed;
  for (let p = 0; p < w * h; p++) {
    const i = p * 4;
    if (colorDist(data[i], data[i + 1], data[i + 2], sr, sg, sb) <= tol) {
      mask[p] = 255;
    }
  }
  return mask;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { colorDist, floodFill, byColorMask };
}
