export function formatScore(score) {
  return Number.isInteger(score) ? String(score) : score.toFixed(2);
}
