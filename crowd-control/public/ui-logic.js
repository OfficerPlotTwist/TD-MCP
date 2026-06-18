export function visibleControls(config, role) {
  if (role === 'master') return config.controls.slice();
  if (role === 'guest') return config.controls.filter((c) => c.role === 'public');
  return [];
}

export function gridVisible(config, role) {
  if (!config.grid) return false;
  if (role === 'master') return true;
  if (role === 'guest') return config.grid.role === 'public';
  return false;
}

export function lockoutSeconds(retryInMs) {
  return Math.ceil(retryInMs / 1000);
}
