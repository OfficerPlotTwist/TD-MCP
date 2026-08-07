// Pure bitmap ops shared by the webapp and node tests.
// A Bitmap is { w, h, data: Uint8Array } with values 0/1. Ops return new bitmaps.

export function makeBitmap(w, h) {
  return { w, h, data: new Uint8Array(w * h) };
}

export function cloneBitmap(bm) {
  return { w: bm.w, h: bm.h, data: new Uint8Array(bm.data) };
}

export function extractPieces(ids, w, h) {
  const pieces = new Map();
  for (let i = 0; i < w * h; i++) {
    const id = ids[i];
    if (id === 0) continue;
    let bm = pieces.get(id);
    if (!bm) { bm = makeBitmap(w, h); pieces.set(id, bm); }
    bm.data[i] = 1;
  }
  return pieces;
}

export function union(a, b) {
  const out = makeBitmap(a.w, a.h);
  for (let i = 0; i < out.data.length; i++) out.data[i] = a.data[i] | b.data[i];
  return out;
}

export function subtract(a, b) {
  const out = makeBitmap(a.w, a.h);
  for (let i = 0; i < out.data.length; i++) out.data[i] = a.data[i] & (b.data[i] ? 0 : 1);
  return out;
}

export function countPixels(bm) {
  let n = 0;
  for (let i = 0; i < bm.data.length; i++) n += bm.data[i];
  return n;
}

export function fillVoids(bm) {
  const { w, h, data } = bm;
  const outside = new Uint8Array(w * h);
  const stack = [];
  const seed = (i) => {
    if (!data[i] && !outside[i]) { outside[i] = 1; stack.push(i); }
  };
  for (let x = 0; x < w; x++) { seed(x); seed((h - 1) * w + x); }
  for (let y = 0; y < h; y++) { seed(y * w); seed(y * w + w - 1); }
  while (stack.length) {
    const i = stack.pop();
    const x = i % w, y = (i - x) / w;
    if (x > 0) seed(i - 1);
    if (x < w - 1) seed(i + 1);
    if (y > 0) seed(i - w);
    if (y < h - 1) seed(i + w);
  }
  const out = makeBitmap(w, h);
  for (let i = 0; i < w * h; i++) out.data[i] = outside[i] ? 0 : 1;
  return out;
}

export function dilate(bm) {
  const { w, h, data } = bm;
  const out = makeBitmap(w, h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let v = 0;
      for (let dy = -1; dy <= 1 && !v; dy++) {
        const ny = y + dy;
        if (ny < 0 || ny >= h) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= w) continue;
          if (data[ny * w + nx]) { v = 1; break; }
        }
      }
      out.data[y * w + x] = v;
    }
  }
  return out;
}

export function erode(bm) {
  const { w, h, data } = bm;
  const out = makeBitmap(w, h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let v = 1;
      for (let dy = -1; dy <= 1 && v; dy++) {
        const ny = y + dy;
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= w || ny < 0 || ny >= h || !data[ny * w + nx]) { v = 0; break; }
        }
      }
      out.data[y * w + x] = v;
    }
  }
  return out;
}
