"""
JWT authentication views.
Provides login, token refresh, and current-user endpoints.
"""

from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile


def _get_user_region(user):
    """Return the region string for a user, or '' for admins."""
    try:
        return user.profile.region
    except UserProfile.DoesNotExist:
        return ''


def _user_payload(user):
    """Build the user info dict returned by login and me endpoints."""
    return {
        'id': user.id,
        'username': user.username,
        'is_staff': user.is_staff,
        'region': _get_user_region(user),
    }


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    POST /api/auth/login/
    Body: { "username": "...", "password": "..." }
    Returns: { "access": "...", "refresh": "...", "user": {...} }
    """
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '')

    if not username or not password:
        return Response(
            {'error': 'Username and password are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(username=username, password=password)
    if user is None:
        return Response(
            {'error': 'Invalid username or password.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    refresh = RefreshToken.for_user(user)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': _user_payload(user),
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def token_refresh(request):
    """
    POST /api/auth/refresh/
    Body: { "refresh": "..." }
    Returns: { "access": "...", "refresh": "..." }
    """
    refresh_token = request.data.get('refresh')
    if not refresh_token:
        return Response(
            {'error': 'Refresh token is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        token = RefreshToken(refresh_token)
        return Response({
            'access': str(token.access_token),
            'refresh': str(token),
        })
    except Exception:
        return Response(
            {'error': 'Invalid or expired refresh token.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    """
    GET /api/auth/me/
    Returns the current authenticated user's info.
    """
    return Response(_user_payload(request.user))
