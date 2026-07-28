"""AI content generation, behind one provider-agnostic call.

The panel stores its own API key and model per provider (SiteSetting), so keys
can be rotated from the settings page without a redeploy; `settings.ANTHROPIC_API_KEY`
remains the fallback for the Claude side.

Note on Claude subscriptions: a Claude Max/Pro plan authorizes a person using
Anthropic's own apps and is not an API credential — there is no way to point a
server at one. Both providers here need a real API key, billed separately.
"""

import anthropic
from django.conf import settings

# Enough headroom for a full article. On current Claude models `max_tokens`
# caps thinking *and* response text together, so a tight budget truncates the
# answer mid-sentence rather than erroring.
MAX_TOKENS = 16000
OPENAI_URL = 'https://api.openai.com/v1/chat/completions'
TIMEOUT = 120.0

STYLE_LABELS = {
    'formal': 'رسمی و حرفه‌ای',
    'informal': 'غیررسمی و صمیمی',
    'technical': 'فنی و تخصصی',
}


class AIError(Exception):
    """Raised with a Persian, user-facing message — surfaced straight to the panel."""


def _prompt(topic: str, style: str) -> str:
    style_text = STYLE_LABELS.get(style, STYLE_LABELS['formal'])
    return (
        f'لطفاً یک مقاله وبلاگ به فارسی با لحن {style_text} بنویسید.\n'
        f'مقاله باید شامل عنوان، خلاصه کوتاه و محتوای کامل باشد.\n'
        f'موضوع مقاله در حوزه ابزارآلات و مصالح ساختمانی است.\n\n'
        f'موضوع: {topic}'
    )


def _anthropic(site, prompt: str) -> str:
    key = site.anthropic_api_key or settings.ANTHROPIC_API_KEY
    if not key:
        raise AIError('کلید API کلاد تنظیم نشده است. از بخش تنظیمات آن را وارد کنید.')

    client = anthropic.Anthropic(api_key=key)
    try:
        message = client.messages.create(
            model=site.anthropic_model or 'claude-opus-5',
            max_tokens=MAX_TOKENS,
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


def _openai(site, prompt: str) -> str:
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
                'max_completion_tokens': MAX_TOKENS,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=TIMEOUT,
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


PROVIDERS = {'anthropic': _anthropic, 'openai': _openai}


def generate_article(topic: str, style: str = 'formal', site=None) -> str:
    """Generate article text with whichever provider the panel is configured for."""
    from .models import SiteSetting

    site = site or SiteSetting.load()
    provider = PROVIDERS.get(site.ai_provider)
    if provider is None:
        raise AIError('سرویس هوش مصنوعی انتخاب‌شده پشتیبانی نمی‌شود.')
    return provider(site, _prompt(topic, style))
