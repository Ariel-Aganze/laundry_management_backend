import getpass
import os

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
        parser.add_argument(
            "--from-env",
            action="store_true",
            help=(
                "Read ADMIN_USERNAME / ADMIN_PASSWORD / ADMIN_EMAIL / ADMIN_FIRST_NAME from the environment. "
                "Does nothing if those are unset or the user already exists (safe to run on every deploy)."
            ),
        )

    def handle(self, *args, **options):
        if options["from_env"]:
            username = os.environ.get("ADMIN_USERNAME", "").strip()
            password = os.environ.get("ADMIN_PASSWORD", "")
            if not username or not password:
                self.stdout.write("createadmin --from-env: ADMIN_USERNAME/ADMIN_PASSWORD not set, skipping.")
                return
            if User.objects.filter(username__iexact=username).exists():
                self.stdout.write(f"createadmin --from-env: '{username}' already exists, skipping.")
                return
            options.update(
                username=username,
                password=password,
                email=os.environ.get("ADMIN_EMAIL", ""),
                first_name=os.environ.get("ADMIN_FIRST_NAME", ""),
            )

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
