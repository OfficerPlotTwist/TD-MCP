// Pure bitmap ops shared by the webapp and node tests.
// A Bitmap is { w, h, data: Uint8Array } with values 0/1. Ops return new bitmaps.

export function makeBitmap(w, h) {
  return { w, h, data: new Uint8Array(w * h) };
}

export function cloneBitmap(bm) {
  return { w: bm.w, h: bm.h, data: new Uint8Array(bm.data) };
}

// Connected-component split (8-connectivity): pixels join a piece only when they
// share the same nonzero id AND touch. Keys are sequential 1..N in scan order.
export function extractPieces(ids, w, h) {
  const pieces = new Map();
  const seen = new Uint8Array(w * h);
  let next = 1;
  for (let start = 0; start < w * h; start++) {
    if (seen[start] || ids[start] === 0) continue;
    const id = ids[start];
    const bm = makeBitmap(w, h);
    const stack = [start];
    seen[start] = 1;
    while (stack.length) {
      const i = stack.pop();
      bm.data[i] = 1;
      const x = i % w, y = (i - x) / w;
      for (let dy = -1; dy <= 1; dy++) {
        const ny = y + dy;
        if (ny < 0 || ny >= h) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= w) continue;
          const ni = ny * w + nx;
          if (!seen[ni] && ids[ni] === id) { seen[ni] = 1; stack.push(ni); }
        }
      }
    }
    pieces.set(next++, bm);
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

// Even-odd scanline fill of the polygon formed by closing points end->start.
export function rasterizeLoop(points, w, h) {
  const out = makeBitmap(w, h);
  if (!points || points.length < 3) return out;
  for (let y = 0; y < h; y++) {
    const yc = y + 0.5;
    const xs = [];
    for (let i = 0; i < points.length; i++) {
      const a = points[i], b = points[(i + 1) % points.length];
      if ((a.y <= yc && b.y > yc) || (b.y <= yc && a.y > yc)) {
        xs.push(a.x + ((yc - a.y) / (b.y - a.y)) * (b.x - a.x));
      }
    }
    xs.sort((p, q) => p - q);
    for (let k = 0; k + 1 < xs.length; k += 2) {
      const x0 = Math.max(0, Math.ceil(xs[k] - 0.5));
      const x1 = Math.min(w - 1, Math.floor(xs[k + 1] - 0.5));
      for (let x = x0; x <= x1; x++) out.data[y * w + x] = 1;
    }
  }
  return out;
}

export function fractionInside(piece, region) {
  let total = 0, inside = 0;
  for (let i = 0; i < piece.data.length; i++) {
    if (piece.data[i]) { total++; if (region.data[i]) inside++; }
  }
  return total === 0 ? 0 : inside / total;
}

export function pointNearPiece(bm, x, y, tol) {
  const x0 = Math.max(0, Math.round(x) - tol), x1 = Math.min(bm.w - 1, Math.round(x) + tol);
  const y0 = Math.max(0, Math.round(y) - tol), y1 = Math.min(bm.h - 1, Math.round(y) + tol);
  for (let yy = y0; yy <= y1; yy++)
    for (let xx = x0; xx <= x1; xx++)
      if (bm.data[yy * bm.w + xx]) return true;
  return false;
}

export function makeHistory(limit = 50) {
  const stack = [];
  return {
    push(pieceId, bitmap) {
      stack.push({ pieceId, bitmap: cloneBitmap(bitmap) });
      if (stack.length > limit) stack.shift();
    },
    pop() { return stack.pop() || null; },
    get length() { return stack.length; },
  };
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
