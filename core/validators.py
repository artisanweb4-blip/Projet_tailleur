# Politique de mot de passe unique pour toute la plateforme.
#
# Règle : 8 caractères minimum, au moins une majuscule, une minuscule,
# un chiffre et un caractère spécial. Elle s'applique :
#   * à l'inscription d'un atelier (core.forms) ;
#   * à la création d'utilisateurs depuis l'application (UtilisateurCreationForm) ;
#   * au changement de mot de passe depuis la page Mon profil
#     (PasswordChangeForm passe par AUTH_PASSWORD_VALIDATORS) ;
#   * à la création de boutiques et d'utilisateurs depuis le back-office
#     saas_admin (validate_password appelé explicitement) ;
#   * au site d'administration Django et à createsuperuser
#     (AUTH_PASSWORD_VALIDATORS).
# Les mots de passe déjà en base restent valides pour se connecter : la
# politique s'applique à toute création ou modification.
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class MotDePasseFortValidator:
    """8 caractères minimum : majuscule, minuscule, chiffre et spécial."""

    MIN = 8

    def validate(self, password, user=None):
        erreurs = []
        if len(password) < self.MIN:
            erreurs.append(
                _(f"au moins {self.MIN} caractères (ici {len(password)})"))
        if not any(c.isupper() for c in password):
            erreurs.append(_("au moins une majuscule"))
        if not any(c.islower() for c in password):
            erreurs.append(_("au moins une minuscule"))
        if not any(c.isdigit() for c in password):
            erreurs.append(_("au moins un chiffre"))
        if not any(not c.isalnum() for c in password):
            erreurs.append(_("au moins un caractère spécial (!, @, #, …)"))
        if erreurs:
            raise ValidationError(
                _("Mot de passe trop faible : il faut %(erreurs)s."),
                code='password_too_weak',
                params={'erreurs': ', '.join(erreurs)},
            )

    def get_help_text(self):
        return _(
            "Au moins 8 caractères, avec une majuscule, une minuscule, "
            "un chiffre et un caractère spécial.")


def mot_de_passe_conforme(password):
    """True si le mot de passe respecte la politique (utilisé par les tests)."""
    try:
        MotDePasseFortValidator().validate(password)
        return True
    except ValidationError:
        return False


def generer_mot_de_passe_temporaire():
    """Mot de passe temporaire conforme à la politique (réinitialisations)."""
    from django.utils.crypto import get_random_string
    return 'T' + get_random_string(4, 'abcdefghijkmnopqrstuvwxyz') \
        + get_random_string(2, '23456789') + '!' + get_random_string(2, 'ABCDEFGHJKLMNPQRSTUVWXYZ')
