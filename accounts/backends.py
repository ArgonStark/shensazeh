from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authenticate a user by email + password.

    The custom User model uses ``mobile`` as USERNAME_FIELD, so the default
    ModelBackend can't log users in by email. This backend fills that gap.
    SMS/OTP login will be added later alongside this.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        email = kwargs.get('email') or username
        if not email or password is None:
            return None

        try:
            user = UserModel.objects.get(email__iexact=email.strip())
        except UserModel.DoesNotExist:
            # Run the default password hasher once to reduce timing attacks.
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            user = UserModel.objects.filter(email__iexact=email.strip()).order_by('pk').first()

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
