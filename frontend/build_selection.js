export class BuildSelectionStore {
  constructor() {
    this.items = new Map();
  }

  ensure(robotId, defaults = {}) {
    if (!this.items.has(robotId)) {
      this.items.set(robotId, {
        selected: false,
        highLevel: Boolean(defaults.highLevel),
        lowLevel: Boolean(defaults.lowLevel),
      });
    }
    return this.items.get(robotId);
  }

  get(robotId) {
    const value = this.items.get(robotId);
    return value ? { ...value } : null;
  }

  setSelected(robotId, selected) {
    const item = this.ensure(robotId);
    item.selected = Boolean(selected);
  }

  setPack(robotId, pack, enabled) {
    const item = this.ensure(robotId);
    if (pack !== 'highLevel' && pack !== 'lowLevel') {
      throw new Error(`Unknown build pack: ${pack}`);
    }
    item[pack] = Boolean(enabled);
  }

  selectedItems() {
    return [...this.items.entries()]
      .filter(([, item]) => item.selected)
      .map(([robotId, item]) => ({
        robot_id: robotId,
        high_level: item.highLevel,
        low_level: item.lowLevel,
      }));
  }
}
