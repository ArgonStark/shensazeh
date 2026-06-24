from django import template
import jdatetime

register = template.Library()


@register.simple_tag(takes_context=True)
def active_nav(context, url_name):
    request = context.get('request')
    if request and hasattr(request, 'resolver_match') and request.resolver_match:
        current = request.resolver_match.url_name
        if current == url_name:
            return 'text-white bg-indigo-600'
    return 'text-gray-400 hover:text-white hover:bg-white/10'


@register.filter
def to_jalali(value):
    if not value:
        return ''
    try:
        jdt = jdatetime.datetime.fromgregorian(datetime=value)
        return jdt.strftime('%Y/%m/%d %H:%M')
    except Exception:
        return str(value)


@register.filter
def to_jalali_date(value):
    if not value:
        return ''
    try:
        jdt = jdatetime.datetime.fromgregorian(datetime=value)
        return jdt.strftime('%Y/%m/%d')
    except Exception:
        return str(value)


PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹'


@register.filter
def persian_number(value):
    result = str(value)
    for i, d in enumerate('0123456789'):
        result = result.replace(d, PERSIAN_DIGITS[i])
    return result
