class UnicodeSlugConverter:
    """Like Django's built-in ``slug`` converter, but accepts Unicode word
    characters so it matches ``SlugField(allow_unicode=True)``.

    The built-in converter's regex is ``[-a-zA-Z0-9_]+``, which cannot match
    Persian slugs such as ``ابزارآلات-برقی`` and makes ``{% url %}`` /
    ``reverse()`` raise NoReverseMatch. ``\\w`` matches Unicode letters and
    digits on ``str`` patterns by default, so this stays URL-safe (no ``/``,
    space, or dot) while allowing the slugs we actually store.
    """

    regex = r'[-\w]+'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
