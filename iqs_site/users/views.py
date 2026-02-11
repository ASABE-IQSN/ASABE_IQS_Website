from events.models import Team
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .forms import CustomUserCreationForm
from .tasks import assign_user_to_teams
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.utils.encoding import force_bytes
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_decode
from django.http import HttpResponse
from django.contrib.sites.models import Site
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import cache_control
from django.views.decorators.vary import vary_on_cookie
from django.utils import timezone
from users.models import GroupProfile, TeamEmail, TeamEnrollmentRequest

@login_required
def account(request):
    user = request.user

    # Teams where the user is a member
    teams_member = Team.objects.filter(
        group_profile__group__user=user
    ).distinct()

    # Teams where the user is an admin
    teams_admin = Team.objects.filter(
        group_profile__admins=user
    ).distinct()

    # Handle enrollment request submission
    if request.method == "POST":
        team_id = request.POST.get("team_id")
        message = request.POST.get("message", "").strip()

        if team_id:
            team = get_object_or_404(Team, team_id=team_id)

            # Check if user is already a member
            if teams_member.filter(team_id=team_id).exists():
                messages.error(request, f"You are already a member of {team.team_name}.")
            else:
                # Check for existing pending request
                existing = TeamEnrollmentRequest.objects.filter(
                    user=user,
                    team=team,
                    status='pending'
                ).exists()

                if existing:
                    messages.error(request, f"You already have a pending request for {team.team_name}.")
                else:
                    # Create the request
                    enrollment_request = TeamEnrollmentRequest.objects.create(
                        user=user,
                        team=team,
                        message=message if message else None
                    )

                    # Send email notification to team admins (async via Celery)
                    from users.tasks import notify_team_admins_of_request
                    notify_team_admins_of_request.delay(enrollment_request.request_id)

                    messages.success(request, f"Your request to join {team.team_name} has been sent to team admins.")

        return redirect("users:account")

    # Get available teams (not a member, no pending request)
    member_team_ids = teams_member.values_list('team_id', flat=True)
    pending_request_team_ids = TeamEnrollmentRequest.objects.filter(
        user=user,
        status='pending'
    ).values_list('team_id', flat=True)

    available_teams = Team.objects.exclude(
        team_id__in=list(member_team_ids) + list(pending_request_team_ids)
    ).order_by('team_name')

    # Get user's pending requests with team details
    pending_requests = TeamEnrollmentRequest.objects.filter(
        user=user,
        status='pending'
    ).select_related('team')

    return render(request, "account.html", {
        "user": user,
        "teams_member": teams_member,
        "teams_admin": teams_admin,
        "available_teams": available_teams,
        "pending_requests": pending_requests,
        "active_page": "my account",
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

        # Existing member management
        if action == "add":
            username = request.POST.get("username")
            if username:
                try:
                    user_to_add = User.objects.get(username=username)
                    group.user_set.add(user_to_add)
                    messages.success(request, f"Added {user_to_add.username} to {team}.")
                except User.DoesNotExist:
                    messages.error(request, f"User '{username}' not found.")

        elif action == "remove":
            user_id = request.POST.get("user_id")
            if user_id:
                try:
                    user_to_remove = User.objects.get(pk=user_id)
                    group.user_set.remove(user_to_remove)
                    # Also remove from admins if they were an admin
                    gp.admins.remove(user_to_remove)
                    messages.success(request, f"Removed {user_to_remove.username} from {team}.")
                except User.DoesNotExist:
                    messages.error(request, "User does not exist.")

        # NEW: Make a member an admin
        elif action == "make_admin":
            user_id = request.POST.get("user_id")
            if user_id:
                try:
                    user_to_promote = User.objects.get(pk=user_id)
                    # Check if user is a member of the team
                    if group.user_set.filter(pk=user_id).exists():
                        gp.admins.add(user_to_promote)
                        messages.success(request, f"Made {user_to_promote.username} an admin of {team}.")
                    else:
                        messages.error(request, "User is not a member of this team.")
                except User.DoesNotExist:
                    messages.error(request, "User does not exist.")

        # NEW: Remove admin status (demote to regular member)
        elif action == "remove_admin":
            user_id = request.POST.get("user_id")
            if user_id:
                try:
                    user_to_demote = User.objects.get(pk=user_id)
                    gp.admins.remove(user_to_demote)
                    messages.success(request, f"Removed admin status from {user_to_demote.username}.")
                except User.DoesNotExist:
                    messages.error(request, "User does not exist.")

        # NEW: Approve enrollment request
        elif action == "approve_request":
            request_id = request.POST.get("request_id")
            if request_id:
                try:
                    enrollment_request = TeamEnrollmentRequest.objects.get(
                        request_id=request_id,
                        team=team,
                        status='pending'
                    )
                    # Add user to group
                    group.user_set.add(enrollment_request.user)
                    # Update request status
                    enrollment_request.status = 'approved'
                    enrollment_request.reviewed_by = request.user
                    enrollment_request.reviewed_at = timezone.now()
                    enrollment_request.save()

                    messages.success(request, f"Approved {enrollment_request.user.username}'s request to join the team.")
                except TeamEnrollmentRequest.DoesNotExist:
                    messages.error(request, "Enrollment request not found or already processed.")

        # NEW: Reject enrollment request
        elif action == "reject_request":
            request_id = request.POST.get("request_id")
            if request_id:
                try:
                    enrollment_request = TeamEnrollmentRequest.objects.get(
                        request_id=request_id,
                        team=team,
                        status='pending'
                    )
                    enrollment_request.status = 'rejected'
                    enrollment_request.reviewed_by = request.user
                    enrollment_request.reviewed_at = timezone.now()
                    enrollment_request.save()

                    messages.success(request, f"Rejected {enrollment_request.user.username}'s request.")
                except TeamEnrollmentRequest.DoesNotExist:
                    messages.error(request, "Enrollment request not found or already processed.")

        return redirect("users:manage_team_members", team_id=team.team_id)

    # Get pending enrollment requests for this team
    pending_requests = TeamEnrollmentRequest.objects.filter(
        team=team,
        status='pending'
    ).select_related('user').order_by('requested_at')

    # Get list of admin user IDs for this team
    admin_user_ids = list(gp.admins.values_list('id', flat=True))

    return render(request, "teams/manage_team_members.html", {
        "team": team,
        "members": members,
        "pending_requests": pending_requests,
        "admin_user_ids": admin_user_ids,
        "active_page": "my account",
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
    
    #current_site = get_current_site(request)
    
    current_site=Site(domain="iqsconnect.org")
    #current_site="127.0.0.1:8000"
    #print(current_site)
    #print(request.get_host())
    #print(request.build_absolute_uri())
    #print(request.session)
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

        # Trigger team assignment task asynchronously
        print("queuing assignment")
        assign_user_to_teams.delay(user.pk)

        login(request, user)
        return redirect("users:account")
    else:
        return HttpResponse("Invalid or expired verification link.")
    
@cache_control(private=True, max_age=30)
def auth_status(request):
    return JsonResponse({
        "authenticated": request.user.is_authenticated,
        "csrfToken": get_token(request),
        "accountUrl": "/user/account/",  # or reverse() if you prefer
        "loginUrl": "/accounts/login/",
        "logoutUrl": "/accounts/logout/",
    })