export function rotatePoint([x, y, z], yaw, pitch) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw);
  const cp = Math.cos(pitch), sp = Math.sin(pitch);
  const rx = x * cy + z * sy;
  const rz = -x * sy + z * cy;
  return [rx, y * cp - rz * sp, y * sp + rz * cp];
}

export function projectPoint(position, width, height, yaw, pitch, cameraDistance) {
  const rotated = rotatePoint(position, yaw, pitch);
  const depth = Math.max(1, cameraDistance - rotated[2]);
  const scale = Math.min(width, height) * 0.9 / depth;
  return { x: width / 2 + rotated[0] * scale, y: height / 2 - rotated[1] * scale, scale, depth };
}

export function buildVisualData(result) {
  const jd = result.points_3d.jd.map(point => ({ ...point, matched: false }));
  const resume = result.points_3d.resume.map(point => ({ ...point, matched: false }));
  const collisions = [];
  for (const match of result.matched) {
    const a = jd[match.jd_index];
    const b = resume[match.resume_index];
    if (!a || !b) continue;
    a.matched = true;
    b.matched = true;
    collisions.push({
      jd: a,
      resume: b,
      similarity: match.similarity,
      credit: match.credit,
      position: a.position.map((value, index) => (value + b.position[index]) / 2),
    });
  }
  return { jd, resume, collisions };
}

export function findClosestTarget(targets, x, y) {
  let closest = null;
  let minDistance = Infinity;
  // Later targets were drawn on top, so they win when positions coincide.
  for (let index = targets.length - 1; index >= 0; index--) {
    const target = targets[index];
    const distance = Math.hypot(target.x - x, target.y - y);
    if (distance < target.radius && distance < minDistance) {
      closest = target;
      minDistance = distance;
    }
  }
  return closest;
}

export function cameraForKey(camera, key) {
  const next = { ...camera };
  if (key === 'ArrowLeft') next.yaw -= 0.18;
  if (key === 'ArrowRight') next.yaw += 0.18;
  if (key === 'ArrowUp') next.pitch = Math.max(-1.25, next.pitch - 0.18);
  if (key === 'ArrowDown') next.pitch = Math.min(1.25, next.pitch + 0.18);
  if (key === '+' || key === '=') next.distance = Math.max(4.2, next.distance - 0.4);
  if (key === '-' || key === '_') next.distance = Math.min(10, next.distance + 0.4);
  return next;
}
