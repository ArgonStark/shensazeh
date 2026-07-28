"""AI content generation, behind one provider-agnostic call.

The panel stores its own API key and model per provider (SiteSetting), so keys
can be rotated from the settings page without a redeploy; `settings.ANTHROPIC_API_KEY`
remains the fallback for the Claude side.

Three providers: Anthropic's own SDK, OpenAI, and OpenRouter (which fronts
~370 models from every vendor behind one OpenAI-shaped endpoint and one key).

Note on Claude subscriptions: a Claude Max/Pro plan authorizes a person using
Anthropic's own apps and is not an API credential — there is no way to point a
server at one. Every provider here needs a real API key, billed separately.
"""

import anthropic
from django.conf import settings

# Enough headroom for a full article. On current Claude models `max_tokens`
# caps thinking *and* response text together, so a tight budget truncates the
# answer mid-sentence rather than erroring.
MAX_TOKENS = 16000
OPENAI_URL = 'https://api.openai.com/v1/chat/completions'
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
OPENROUTER_MODELS_URL = 'https://openrouter.ai/api/v1/models'
TIMEOUT = 120.0
_MODELS_CACHE_KEY = 'openrouter:models:v1'
_MODELS_CACHE_SECONDS = 6 * 60 * 60

STYLE_LABELS = {
    'formal': 'رسمی و حرفه‌ای',
    'informal': 'غیررسمی و صمیمی',
    'technical': 'فنی و تخصصی',
}

# What to write, per panel section. The blog wants an article; a service or
# project page wants sales copy with a different shape, so one prompt for all
# three produced blog posts in the wrong places.
KIND_PROMPTS = {
    'blog': (
        'یک مقاله وبلاگ به فارسی بنویس.\n'
        'شامل عنوان، خلاصه کوتاه و محتوای کامل با تیترهای میانی.'
    ),
    'service': (
        'یک متن معرفی برای صفحه یک «خدمت» به فارسی بنویس.\n'
        'شامل توضیح خدمت، مزایا، مراحل انجام کار و یک دعوت به تماس در پایان.\n'
        'از تیترهای میانی کوتاه استفاده کن. عنوان تکراری در ابتدای متن نیاور.'
    ),
    'project': (
        'یک متن معرفی برای صفحه یک «پروژه» اجرا شده به فارسی بنویس.\n'
        'شامل معرفی پروژه، چالش‌ها، راهکار اجرا شده و نتیجه نهایی.\n'
        'از تیترهای میانی کوتاه استفاده کن. عنوان تکراری در ابتدای متن نیاور.'
    ),
}


class AIError(Exception):
    """Raised with a Persian, user-facing message — surfaced straight to the panel."""


def _proxy(site) -> str | None:
    """Optional outbound proxy.

    Blank by default — all three providers are reachable directly from the
    production host. It exists because OpenRouter's WAF will return 403
    "Access denied by security policy" for a burst of rapid requests from one
    IP, and a provider could geo-block a datacenter range outright; when that
    happens a proxy is the difference between usable and not.
    """
    return (getattr(site, 'ai_proxy_url', '') or '').strip() or None


def _prompt(topic: str, style: str, kind: str = 'blog') -> str:
    style_text = STYLE_LABELS.get(style, STYLE_LABELS['formal'])
    task = KIND_PROMPTS.get(kind, KIND_PROMPTS['blog'])
    return (
        f'{task}\n'
        f'لحن نوشتار: {style_text}.\n'
        f'حوزه کاری مجموعه: ابزارآلات، مصالح ساختمانی و مقاوم‌سازی سازه.\n'
        f'خروجی را به صورت HTML ساده بده (فقط p, h2, h3, ul, li, strong).\n'
        f'هیچ توضیح اضافه‌ای خارج از متن ننویس.\n\n'
        f'موضوع: {topic}'
    )


def _anthropic(site, prompt: str, max_tokens: int = MAX_TOKENS) -> str:
    key = site.anthropic_api_key or settings.ANTHROPIC_API_KEY
    if not key:
        raise AIError('کلید API کلاد تنظیم نشده است. از بخش تنظیمات آن را وارد کنید.')

    proxy = _proxy(site)
    if proxy:
        from anthropic import DefaultHttpxClient
        client = anthropic.Anthropic(api_key=key, http_client=DefaultHttpxClient(proxy=proxy))
    else:
        client = anthropic.Anthropic(api_key=key)
    try:
        message = client.messages.create(
            model=site.anthropic_model or 'claude-opus-5',
            max_tokens=max_tokens,
            messages=[{'role': 'user', 'content': prompt}],
        )
    except anthropic.AuthenticationError:
        raise AIError('کلید API کلاد معتبر نیست.')
    except anthropic.RateLimitError:
        raise AIError('محدودیت درخواست کلاد. کمی بعد دوباره تلاش کنید.')
    except anthropic.APIStatusError as exc:
        raise AIError(f'خطای سرویس کلاد ({exc.status_code}).')
    except anthropic.APIConnectionError:
        raise AIError('اتصال به سرویس کلاد برقرار نشد.')

    # A safety decline returns HTTP 200 with an empty content list, so this has
    # to be checked before indexing into the response.
    if message.stop_reason == 'refusal':
        raise AIError('این درخواست توسط سرویس کلاد رد شد. موضوع دیگری را امتحان کنید.')
    text = ''.join(b.text for b in message.content if b.type == 'text').strip()
    if not text:
        raise AIError('پاسخی از سرویس کلاد دریافت نشد.')
    return text


def _openai(site, prompt: str, max_tokens: int = MAX_TOKENS) -> str:
    import httpx

    key = site.openai_api_key
    if not key:
        raise AIError('کلید API اوپن‌ای‌آی تنظیم نشده است. از بخش تنظیمات آن را وارد کنید.')

    try:
        response = httpx.post(
            OPENAI_URL,
            headers={'Authorization': f'Bearer {key}'},
            json={
                'model': site.openai_model or 'gpt-4o',
                'max_completion_tokens': max_tokens,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=TIMEOUT,
            proxy=_proxy(site),
        )
    except httpx.RequestError:
        raise AIError('اتصال به سرویس اوپن‌ای‌آی برقرار نشد.')

    if response.status_code == 401:
        raise AIError('کلید API اوپن‌ای‌آی معتبر نیست.')
    if response.status_code == 429:
        raise AIError('محدودیت درخواست اوپن‌ای‌آی. کمی بعد دوباره تلاش کنید.')
    if response.status_code >= 400:
        raise AIError(f'خطای سرویس اوپن‌ای‌آی ({response.status_code}).')

    try:
        text = response.json()['choices'][0]['message']['content'].strip()
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise AIError('پاسخ سرویس اوپن‌ای‌آی قابل خواندن نبود.')
    if not text:
        raise AIError('پاسخی از سرویس اوپن‌ای‌آی دریافت نشد.')
    return text


def _openrouter(site, prompt: str, max_tokens: int = MAX_TOKENS) -> str:
    """OpenRouter speaks the OpenAI chat-completions shape across ~370 models.

    Web search, when enabled, is declared as OpenRouter's *server* tools: the
    model decides whether to search, OpenRouter runs the search on its own
    infrastructure and feeds the results back, and we still receive one final
    assistant message. There is no client-side tool loop to run.
    """
    import httpx

    key = site.openrouter_api_key
    if not key:
        raise AIError('کلید API اوپن‌روتر تنظیم نشده است. از بخش تنظیمات آن را وارد کنید.')

    body = {
        'model': site.openrouter_model or 'anthropic/claude-opus-5',
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': prompt}],
    }
    if site.openrouter_web_search:
        body['tools'] = [{'type': 'openrouter:web_search'},
                         {'type': 'openrouter:web_fetch'}]

    try:
        response = httpx.post(
            OPENROUTER_URL,
            headers={
                'Authorization': f'Bearer {key}',
                # OpenRouter attributes usage to the calling site via these.
                'HTTP-Referer': getattr(settings, 'SITE_URL', '') or '',
                'X-Title': 'Shensazeh',
            },
            json=body,
            timeout=TIMEOUT,
            proxy=_proxy(site),
        )
    except httpx.RequestError:
        raise AIError('اتصال به سرویس اوپن‌روتر برقرار نشد.')

    if response.status_code == 401:
        raise AIError('کلید API اوپن‌روتر معتبر نیست.')
    if response.status_code == 402:
        raise AIError('اعتبار حساب اوپن‌روتر کافی نیست.')
    if response.status_code == 403:
        raise AIError('اوپن‌روتر فعلاً درخواست از این سرور را نمی‌پذیرد (۴۰۳). '
                      'معمولاً موقتی است؛ چند دقیقه بعد دوباره تلاش کنید. '
                      'اگر ادامه داشت، پراکسی وارد کنید یا از کلاد/اوپن‌ای‌آی مستقیم استفاده کنید.')
    if response.status_code == 429:
        raise AIError('محدودیت درخواست اوپن‌روتر. کمی بعد دوباره تلاش کنید.')
    if response.status_code >= 400:
        raise AIError(f'خطای سرویس اوپن‌روتر ({response.status_code}).')

    try:
        payload = response.json()
    except ValueError:
        raise AIError('پاسخ سرویس اوپن‌روتر قابل خواندن نبود.')

    # OpenRouter reports upstream provider failures as 200 + an error object.
    if isinstance(payload.get('error'), dict):
        raise AIError(f"خطای مدل: {payload['error'].get('message', 'نامشخص')}")

    try:
        text = (payload['choices'][0]['message']['content'] or '').strip()
    except (KeyError, IndexError, TypeError):
        raise AIError('پاسخ سرویس اوپن‌روتر قابل خواندن نبود.')
    if not text:
        raise AIError('پاسخی از مدل انتخاب‌شده دریافت نشد. مدل دیگری را امتحان کنید.')
    return text


PROVIDERS = {'anthropic': _anthropic, 'openai': _openai, 'openrouter': _openrouter}


def generate_article(topic: str, style: str = 'formal', site=None, kind: str = 'blog') -> str:
    """Generate content with whichever provider the panel is configured for."""
    from .models import SiteSetting

    site = site or SiteSetting.load()
    provider = PROVIDERS.get(site.ai_provider)
    if provider is None:
        raise AIError('سرویس هوش مصنوعی انتخاب‌شده پشتیبانی نمی‌شود.')
    return provider(site, _prompt(topic, style, kind))


def openrouter_models(api_key: str = '', proxy: str = '') -> list:
    """The live model catalogue, trimmed to what the picker needs.

    Fetched rather than hardcoded: OpenRouter carries ~370 models and the list
    turns over constantly, so a checked-in copy would be wrong within weeks.
    Cached for six hours; the key is optional (the endpoint is public) but is
    sent when present so account-specific availability is reflected.
    """
    import httpx
    from django.core.cache import cache

    cached = cache.get(_MODELS_CACHE_KEY)
    if cached is not None:
        return cached

    headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
    try:
        response = httpx.get(OPENROUTER_MODELS_URL, headers=headers, timeout=30.0,
                             proxy=(proxy or '').strip() or None)
    except httpx.RequestError:
        raise AIError('اتصال به اوپن‌روتر برقرار نشد.')
    if response.status_code == 403:
        raise AIError('اوپن‌روتر فعلاً درخواست از این سرور را نمی‌پذیرد (۴۰۳). '
                      'معمولاً موقتی است؛ چند دقیقه بعد دوباره تلاش کنید. '
                      'اگر ادامه داشت، پراکسی وارد کنید یا از کلاد/اوپن‌ای‌آی مستقیم استفاده کنید.')
    try:
        response.raise_for_status()
        raw = response.json()['data']
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise AIError('دریافت فهرست مدل‌ها از اوپن‌روتر ناموفق بود.')

    models = []
    for item in raw:
        pricing = item.get('pricing') or {}
        models.append({
            'id': item.get('id', ''),
            'name': item.get('name') or item.get('id', ''),
            'context': item.get('context_length') or 0,
            # Per-token strings -> dollars per million, which is how the
            # provider price lists everyone compares against are quoted.
            'in': _per_million(pricing.get('prompt')),
            'out': _per_million(pricing.get('completion')),
            'tools': 'tools' in (item.get('supported_parameters') or []),
        })
    models.sort(key=lambda m: m['id'])
    cache.set(_MODELS_CACHE_KEY, models, _MODELS_CACHE_SECONDS)
    return models


def _per_million(value) -> float:
    try:
        return round(float(value) * 1_000_000, 4)
    except (TypeError, ValueError):
        return 0.0


def test_connection(site=None) -> str:
    """Round-trip the configured provider with a near-zero-cost request.

    Turns "خطا در ارتباط با سرور" into a specific answer: wrong key, no credit,
    IP refused, or working. Costs a fraction of a cent — it is a real call,
    because only a real call proves the key and the network path together.
    """
    from .models import SiteSetting

    site = site or SiteSetting.load()
    provider = PROVIDERS.get(site.ai_provider)
    if provider is None:
        raise AIError('سرویس هوش مصنوعی انتخاب‌شده پشتیبانی نمی‌شود.')
    provider(site, 'بگو: سلام', max_tokens=16)
    label = dict(SiteSetting.AI_PROVIDER_CHOICES).get(site.ai_provider, site.ai_provider)
    return f'اتصال به {label} برقرار است.'
