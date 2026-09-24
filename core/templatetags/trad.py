"""Tag {% tr "…" %} : traduit une chaîne selon la langue de la session."""
from django import template

from core.traduction import traduire

register = template.Library()


@register.simple_tag(takes_context=True)
def tr(context, texte):
    """Traduit `texte` ; les phrases de type « Juillet 2026 » sont
    décomposées (mois + année) pour couvrir tous les intitulés de mois
    sans remplir le dictionnaire de combinaisons."""
    langue = context.get('langue', 'fr')
    if langue == 'fr' or not texte:
        return texte
    mots = str(texte).strip().split()
    if len(mots) == 2 and mots[1].isdigit():
        mois_traduit = traduire(mots[0], langue)
        if mois_traduit != mots[0]:
            return f'{mois_traduit} {mots[1]}'
    return traduire(texte, langue)
