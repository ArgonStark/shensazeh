/* Alpine component backing admin_panel/components/icon_picker.html.
 *
 * Matches on the icon's own name and on the Persian keywords in BI_FA, so
 * searching "آچار" finds bi-wrench. With an empty query it shows the curated
 * suggestions rather than dumping all ~2000 icons into the DOM.
 */
function iconPicker(initial) {
  return {
    open: false,
    q: '',
    selected: initial || '',
    shown: [],
    total: 0,

    init() {
      const all = window.BI_ICONS || [];
      this.total = all.length;
      this.filter();
    },

    filter() {
      const all = window.BI_ICONS || [];
      const fa = window.BI_FA || {};
      const suggested = window.BI_SUGGESTED || [];
      const q = this.q.trim().toLowerCase();

      if (!q) {
        this.shown = suggested.map((n) => 'bi-' + n);
        return;
      }
      const hits = [];
      for (let i = 0; i < all.length; i++) {
        const name = all[i];
        if (name.indexOf(q) !== -1 || (fa[name] && fa[name].indexOf(q) !== -1)) {
          hits.push('bi-' + name);
          if (hits.length >= 300) break; // cap the DOM, not the search
        }
      }
      this.shown = hits;
    },
  };
}
