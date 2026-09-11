// Nominal UR10e/UR12e DH geometry, meters/radians. Source: UR official DH table.
export const DH = [
  [0, 0.1807, Math.PI / 2], [-0.6127, 0, 0], [-0.57155, 0, 0],
  [0, 0.17415, Math.PI / 2], [0, 0.11985, -Math.PI / 2], [0, 0.11655, 0],
];
const identity = () => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
export function multiply(a, b) {
  return Array.from({length: 16}, (_, i) => {
    const row = Math.floor(i / 4), col = i % 4;
    return [0, 1, 2, 3].reduce((sum, k) => sum + a[row * 4 + k] * b[k * 4 + col], 0);
  });
}
export function frames(q) {
  if (!Array.isArray(q) || q.length !== 6 || !q.every(Number.isFinite)) {
    throw new Error('Six finite actual joint angles are required');
  }
  const result = [identity()];
  q.forEach((theta, i) => {
    const [a, d, alpha] = DH[i];
    const c = Math.cos(theta), s = Math.sin(theta);
    const ca = Math.cos(alpha), sa = Math.sin(alpha);
    result.push(multiply(result.at(-1), [
      c, -s * ca, s * sa, a * c,
      s, c * ca, -c * sa, a * s,
      0, sa, ca, d,
      0, 0, 0, 1,
    ]));
  });
  return result;
}
