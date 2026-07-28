/* Alpine component behind admin_panel/components/ai_assist.html.
 *
 * Appends generated text to the editor instead of replacing it — the previous
 * blog-only version called dangerouslyPasteHTML on the whole document, which
 * silently discarded whatever the writer had already typed.
 */
function aiAssistField(field, kind, endpoint, csrfToken) {
  return {
    topic: '',
    style: 'formal',
    loading: false,

    editor() {
      return window.rtEditors && window.rtEditors[field];
    },

    notify(message, type) {
      if (window.Alpine && Alpine.store('toast')) {
        Alpine.store('toast').show(message, type || 'error');
      } else {
        console.error(message);
      }
    },

    async generate() {
      const titleEl = document.getElementById('id_title') || document.getElementById('id_name');
      const topic = this.topic.trim() || (titleEl ? titleEl.value.trim() : '');
      if (!topic) {
        this.notify('ابتدا عنوان یا موضوعی وارد کنید.', 'warning');
        return;
      }

      const quill = this.editor();
      if (!quill) {
        this.notify('ویرایشگر هنوز آماده نیست.');
        return;
      }

      this.loading = true;
      try {
        const body = new FormData();
        body.append('prompt', topic);
        body.append('style', this.style);
        body.append('kind', kind);
        body.append('csrfmiddlewaretoken', csrfToken);

        const res = await fetch(endpoint, { method: 'POST', body: body });
        const data = await res.json();
        if (!res.ok || !data.content) {
          this.notify(data.error || 'تولید متن ناموفق بود.');
          return;
        }

        // Append at the end, keeping existing content intact.
        const at = quill.getLength() - 1;
        quill.clipboard.dangerouslyPasteHTML(at, data.content);
        quill.setSelection(quill.getLength() - 1);
        this.notify('متن تولید شد.', 'success');
      } catch (e) {
        this.notify('خطا در ارتباط با سرور.');
      } finally {
        this.loading = false;
      }
    },
  };
}
