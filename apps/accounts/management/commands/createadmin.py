import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create the initial Admin account (FR-003)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=False)
        parser.add_argument("--email", default="")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")
        parser.add_argument(
            "--password",
            default=None,
            help="Avoid on shared machines (shell history). If omitted you will be prompted.",
        )

    def handle(self, *args, **options):
        username = options["username"] or input("Username: ").strip()
        if not username:
            raise CommandError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise CommandError(f"User '{username}' already exists.")

        password = options["password"]
        if not password:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Password (again): "):
                raise CommandError("Passwords do not match.")

        user = User(
            username=username,
            email=options["email"].strip().lower(),
            first_name=options["first_name"],
            last_name=options["last_name"],
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin '{username}' created."))
