/* Alpine component for the OpenRouter model picker.
 *
 * The catalogue is ~370 models and changes constantly, so it is fetched from
 * the panel (which caches it server-side) rather than shipped in the page.
 * Loads lazily on first open — a settings page that never touches the AI
 * section shouldn't pay for the request.
 */
function modelPicker(initial, endpoint) {
  return {
    open: false,
    loading: false,
    error: '',
    q: '',
    onlyTools: false,
    selected: initial || '',
    models: [],
    shown: [],

    toggle() {
      this.open = !this.open;
      if (this.open && !this.models.length) this.load();
    },

    async load() {
      this.loading = true;
      this.error = '';
      try {
        const res = await fetch(endpoint, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const data = await res.json();
        if (!res.ok) {
          this.error = data.error || 'دریافت فهرست مدل‌ها ناموفق بود.';
        } else {
          this.models = data.models || [];
          this.filter();
        }
      } catch (e) {
        this.error = 'خطا در ارتباط با سرور.';
      } finally {
        this.loading = false;
      }
    },

    filter() {
      const q = this.q.trim().toLowerCase();
      let list = this.models;
      if (this.onlyTools) list = list.filter((m) => m.tools);
      if (q) {
        list = list.filter(
          (m) => m.id.toLowerCase().indexOf(q) !== -1 || m.name.toLowerCase().indexOf(q) !== -1
        );
      }
      this.shown = list.slice(0, 200); // cap the DOM, not the search
    },

    pick(id) {
      this.selected = id;
      this.open = false;
    },

    price(m) {
      if (!m.in && !m.out) return 'رایگان';
      return '$' + m.in + ' / $' + m.out;
    },

    context(m) {
      if (!m.context) return '';
      return m.context >= 1000 ? Math.round(m.context / 1000) + 'K' : String(m.context);
    },
  };
}
