/* Rich-text editor wiring for the admin panel.
 *
 * Turns every `.rt-editor` div on the page into a Quill instance bound to the
 * hidden textarea named by its data-field. Toolbar image picks are uploaded to
 * the server and inserted as a URL — Quill's default behaviour is to inline the
 * file as a base64 data URI, which would store a whole JPEG in a text column.
 */
(function () {
  'use strict';

  const TOOLBAR = [
    [{ header: [1, 2, 3, false] }],
    ['bold', 'italic', 'underline', 'strike'],
    [{ list: 'ordered' }, { list: 'bullet' }],
    [{ align: [] }],
    ['blockquote', 'code-block'],
    ['link', 'image'],
    ['clean'],
  ];

  function csrfToken() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function toast(message, type) {
    if (window.Alpine && Alpine.store('toast')) {
      Alpine.store('toast').show(message, type || 'error');
    } else {
      console.error(message);
    }
  }

  function uploadImage(quill, uploadUrl) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/gif,image/webp';
    input.onchange = async () => {
      const file = input.files && input.files[0];
      if (!file) return;

      // Placeholder keeps the caret position stable while the upload runs.
      const range = quill.getSelection(true);
      quill.insertText(range.index, 'در حال بارگذاری تصویر…', { italic: true });

      const body = new FormData();
      body.append('image', file);
      try {
        const res = await fetch(uploadUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken() },
          body: body,
        });
        const data = await res.json();
        quill.deleteText(range.index, 'در حال بارگذاری تصویر…'.length);
        if (!res.ok || !data.url) {
          toast(data.error || 'بارگذاری تصویر ناموفق بود.');
          return;
        }
        quill.insertEmbed(range.index, 'image', data.url);
        quill.setSelection(range.index + 1);
      } catch (e) {
        quill.deleteText(range.index, 'در حال بارگذاری تصویر…'.length);
        toast('خطا در ارتباط با سرور هنگام بارگذاری تصویر.');
      }
    };
    input.click();
  }

  // Instances by field name, so page scripts (e.g. the blog AI assistant) can
  // insert into an editor without owning its construction.
  window.rtEditors = window.rtEditors || {};

  function init() {
    const editors = document.querySelectorAll('.rt-editor');
    if (!editors.length) return;
    const uploadUrl = document.body.dataset.editorUploadUrl;

    editors.forEach((el) => {
      const field = el.dataset.field;
      const textarea = document.getElementById('id_' + field);
      if (!textarea) return;

      const quill = new Quill(el, {
        theme: 'snow',
        placeholder: el.dataset.placeholder || '',
        modules: { toolbar: { container: TOOLBAR } },
      });

      // Quill 2 keeps the toolbar LTR; the content area must be RTL.
      quill.root.setAttribute('dir', 'rtl');
      quill.root.style.textAlign = 'right';

      if (uploadUrl) {
        quill.getModule('toolbar').addHandler('image', () => uploadImage(quill, uploadUrl));
      }

      if (textarea.value.trim()) {
        quill.clipboard.dangerouslyPasteHTML(textarea.value);
      }

      window.rtEditors[field] = quill;

      // getSemanticHTML() emits clean markup; innerHTML would carry Quill's
      // internal classes and a trailing <p><br></p> into the database.
      const form = textarea.closest('form');
      if (form) {
        form.addEventListener('submit', () => {
          const html = quill.getSemanticHTML().trim();
          textarea.value = html === '<p></p>' ? '' : html;
        });
      }
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
