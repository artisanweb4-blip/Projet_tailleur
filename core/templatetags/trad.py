"""Tag {% tr "…" %} : traduit une chaîne selon la langue de la session."""
from django import template

from core.traduction import traduire

register = template.Library()


@register.simple_tag(takes_context=True)
def tr(context, texte):
    return traduire(texte, context.get('langue', 'fr'))
