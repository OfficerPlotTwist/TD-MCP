// Tests for maskops.mjs — run with: node touchdesigner/maskcombiner/test_maskops.mjs
import assert from 'node:assert/strict';
import {
  makeBitmap, cloneBitmap, extractPieces, union, subtract, countPixels,
  fillVoids, dilate, erode,
  rasterizeLoop, fractionInside, pointNearPiece, makeHistory,
} from './maskops.mjs';

function bmFromRows(rows) {
  const h = rows.length, w = rows[0].length;
  const bm = makeBitmap(w, h);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++)
      bm.data[y * w + x] = rows[y][x] === '#' ? 1 : 0;
  return bm;
}
function rowsFromBm(bm) {
  const out = [];
  for (let y = 0; y < bm.h; y++) {
    let s = '';
    for (let x = 0; x < bm.w; x++) s += bm.data[y * bm.w + x] ? '#' : '.';
    out.push(s);
  }
  return out;
}

// extractPieces: two ids -> two bitmaps, 0 is background
{
  const ids = new Uint8Array([0, 3, 3, 0, 7, 0]);
  const pieces = extractPieces(ids, 3, 2);
  assert.equal(pieces.size, 2);
  assert.deepEqual(Array.from(pieces.get(3).data), [0, 1, 1, 0, 0, 0]);
  assert.deepEqual(Array.from(pieces.get(7).data), [0, 0, 0, 0, 1, 0]);
}

// union / subtract / countPixels / clone independence
{
  const a = bmFromRows(['##.', '...']);
  const b = bmFromRows(['.#.', '..#']);
  assert.deepEqual(rowsFromBm(union(a, b)), ['##.', '..#']);
  assert.deepEqual(rowsFromBm(subtract(a, b)), ['#..', '...']);
  assert.equal(countPixels(a), 2);
  const c = cloneBitmap(a);
  c.data[0] = 0;
  assert.equal(a.data[0], 1);
}

// fillVoids: donut hole fills, border-open bay does not
{
  const donut = bmFromRows([
    '#####',
    '#...#',
    '#.#.#',
    '#...#',
    '#####',
  ]);
  assert.deepEqual(rowsFromBm(fillVoids(donut)), [
    '#####', '#####', '#####', '#####', '#####',
  ]);
  const bay = bmFromRows([
    '#####',
    '#...#',
    '#####',
    '.....',
    '.....',
  ]);
  // hole in bay is enclosed -> fills; open bottom rows stay empty
  assert.deepEqual(rowsFromBm(fillVoids(bay)), [
    '#####', '#####', '#####', '.....', '.....',
  ]);
}

// dilate / erode, 8-neighbor, border-safe
{
  const dot = bmFromRows(['.....', '..#..', '.....']);
  assert.deepEqual(rowsFromBm(dilate(dot)), ['.###.', '.###.', '.###.']);
  const block = bmFromRows(['###', '###', '###']);
  assert.deepEqual(rowsFromBm(erode(block)), ['...', '.#.', '...']);
  // erode below 3x3 -> empty, never throws
  assert.equal(countPixels(erode(dot)), 0);
}

// rasterizeLoop: axis-aligned square, closed implicitly
{
  const loop = rasterizeLoop(
    [{ x: 1, y: 1 }, { x: 4, y: 1 }, { x: 4, y: 4 }, { x: 1, y: 4 }], 6, 6);
  assert.deepEqual(rowsFromBm(loop), [
    '......',
    '.###..',
    '.###..',
    '.###..',
    '......',
    '......',
  ]);
  // degenerate stroke (<3 points) rasterizes to empty
  assert.equal(countPixels(rasterizeLoop([{ x: 1, y: 1 }, { x: 3, y: 3 }], 6, 6)), 0);
}

// fractionInside
{
  const piece = bmFromRows(['##..', '##..']);
  const region = bmFromRows(['#...', '#...']);
  assert.equal(fractionInside(piece, region), 0.5);
  assert.equal(fractionInside(makeBitmap(4, 2), region), 0);
}

// pointNearPiece: tolerance window
{
  const bm = bmFromRows(['.....', '..#..', '.....']);
  assert.equal(pointNearPiece(bm, 2, 1, 0), true);
  assert.equal(pointNearPiece(bm, 4, 1, 1), false);
  assert.equal(pointNearPiece(bm, 4, 1, 2), true);
  assert.equal(pointNearPiece(bm, -1, -1, 3), true); // window clamps to bounds
}

// history: clone-on-push, LIFO, cap
{
  const h = makeHistory(2);
  const bm = bmFromRows(['#.']);
  h.push(5, bm);
  bm.data[0] = 0;
  h.push(6, bmFromRows(['.#']));
  h.push(7, bmFromRows(['##'])); // evicts pieceId 5
  assert.equal(h.length, 2);
  assert.equal(h.pop().pieceId, 7);
  const last = h.pop();
  assert.equal(last.pieceId, 6);
  assert.equal(last.bitmap.data[0], 0);
  assert.equal(last.bitmap.data[1], 1);
  assert.equal(h.pop(), null);
}

console.log('task2 ok');
