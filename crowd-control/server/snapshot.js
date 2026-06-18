// crowd-control/server/snapshot.js
export function buildSnapshot(session) {
  const slots = [];
  for (let i = 0; i <= session.config.slotCap; i++) {
    const connId = session.slots[i];
    if (!connId) continue;
    const client = session.clients.get(connId);
    const g = session.grid[i] || { x: 0, y: 0 };
    slots.push({
      slot: i,
      role: client ? client.role : (i === 0 ? 'master' : 'guest'),
      active: true,
      x: g.x,
      y: g.y,
      vals: session.values[i] || {},
    });
  }
  return {
    type: 'snapshot',
    code: session.currentCode,
    masterSlot: session.master ? 0 : null,
    slots,
  };
}
