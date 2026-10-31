from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    CommentViewSet,
    PostViewSet,
    ProfileViewSet,
    RegisterView,
    TagViewSet,
)

router = DefaultRouter()
router.register('posts', PostViewSet, basename='post')
router.register('tags', TagViewSet, basename='tag')
router.register('categories', CategoryViewSet, basename='category')
router.register('comments', CommentViewSet, basename='comment')
router.register('profiles', ProfileViewSet, basename='profile')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/token/', TokenObtainPairView.as_view(), name='token-obtain-pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
] + router.urls
