from events.models import Team
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .forms import CustomUserCreationForm
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.utils.encoding import force_bytes
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_decode
from django.http import HttpResponse
from django.contrib.sites.models import Site

@login_required
def account(request):
    user = request.user

    # Teams where the user is a member (via Group membership)
    teams_member = Team.objects.filter(
        group_profile__group__user=user
    ).distinct()

    # Teams where the user is an admin (via GroupProfile.admins)
    teams_admin = Team.objects.filter(
        group_profile__admins=user
    ).distinct()

    return render(request, "account.html", {
        "user": user,
        "teams_member": teams_member,
        "teams_admin": teams_admin,
    })

User = get_user_model()

def is_team_admin(user, team: Team) -> bool:
    gp = getattr(team, "group_profile", None)
    if gp is None:
        return False
    return gp.admins.filter(pk=user.pk).exists()

@login_required
def manage_team_members(request, team_id):
    team = get_object_or_404(Team, team_id=team_id)

    gp = getattr(team, "group_profile", None)
    if gp is None:
        return HttpResponseForbidden("This team has no group profile configured.")

    if not is_team_admin(request.user, team):
        return HttpResponseForbidden("You are not an admin for this team.")

    group = gp.group
    members = group.user_set.all()

    if request.method == "POST":
        action = request.POST.get("action")
        username = request.POST.get("username")
        user_id = request.POST.get("user_id")

        if action == "add" and username:
            try:
                user_to_add = User.objects.get(username=username)
                group.user_set.add(user_to_add)
                messages.success(request, f"Added {user_to_add.username} to {team}.")
            except User.DoesNotExist:
                messages.error(request, f"User '{username}' not found.")

        elif action == "remove" and user_id:
            try:
                user_to_remove = User.objects.get(pk=user_id)
                group.user_set.remove(user_to_remove)
                messages.success(request, f"Removed {user_to_remove.username} from {team}.")
            except User.DoesNotExist:
                messages.error(request, "User does not exist.")

        return redirect("users:manage_team_members", team_id=team.team_id)

    return render(request, "teams/manage_team_members.html", {
        "team": team,
        "members": members,
    })

def signup(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()  # inactive user
            send_verification_email(request, user)
            return render(request, "registration/check_email.html")
    else:
        form = CustomUserCreationForm()

    return render(request, "registration/signup.html", {"form": form})

def send_verification_email(request, user):
    
    current_site = get_current_site(request)
    current_site=Site(domain="127.0.0.1:8000/testing")
    #current_site="127.0.0.1:8000"
    print(current_site)
    print(request.get_host())
    print(request.build_absolute_uri())
    print(request.session)
    subject = "Confirm your email address"
    
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    print(token)

    verify_url = f"https://{current_site.domain}/user/verify-email/{uid}/{token}/"

    message = render_to_string("registration/verify_email_message.txt", {
        "user": user,
        "verify_url": verify_url,
    })

    send_mail(
        subject,
        message,
        "no-reply@internationalquarterscale.com",
        [user.email],
        fail_silently=False,
    )


def verify_email(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, OverflowError):
        user = None
    print(token)
    print(user)
    print(default_token_generator.check_token(user, token))
    if user and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        return redirect("users:account")
    else:
        return HttpResponse("Invalid or expired verification link.")