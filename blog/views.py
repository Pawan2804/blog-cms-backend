from django.db.models import F, Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import Category, Comment, Like, Post, Profile, Tag
from .serializers import (
    CategorySerializer,
    CommentSerializer,
    PostSerializer,
    ProfileSerializer,
    TagSerializer,
    UserRegistrationSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]


class IsProfileOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.user == request.user


class IsAuthorOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return (
            request.method in permissions.SAFE_METHODS
            or request.user.is_staff
            or obj.author == request.user
        )


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    lookup_field = 'slug'
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'author', 'tags__slug', 'categories__slug']
    search_fields = ['title', 'excerpt', 'content', 'tags__name', 'categories__name']
    ordering_fields = ['published_at', 'created_at', 'title']

    def get_queryset(self):
        queryset = Post.objects.select_related('author').prefetch_related('tags')
        if self.request.user.is_staff:
            return queryset
        if self.request.user.is_authenticated:
            return queryset.filter(
                Q(status=Post.Status.PUBLISHED, published_at__lte=timezone.now())
                | Q(author=self.request.user)
            ).distinct()
        return queryset.filter(status=Post.Status.PUBLISHED, published_at__lte=timezone.now())

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        post = self.get_object()
        Post.objects.filter(pk=post.pk).update(view_count=F('view_count') + 1)
        post.refresh_from_db(fields=['view_count'])
        return Response(self.get_serializer(post).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def featured(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset().filter(is_featured=True))
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(queryset, many=True).data)

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def preview(self, request, *args, **kwargs):
        post = self.get_object()
        return Response(self.get_serializer(post).data)

    @action(detail=True, methods=['post', 'delete'], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, *args, **kwargs):
        post = self.get_object()
        if request.method == 'POST':
            _, created = Like.objects.get_or_create(post=post, user=request.user)
            return Response(
                {'liked': True, 'likes_count': post.likes.count()},
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )

        Like.objects.filter(post=post, user=request.user).delete()
        return Response({'liked': False, 'likes_count': post.likes.count()})


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    lookup_field = 'slug'


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = 'slug'


class ProfileViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Profile.objects.select_related('user')
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsProfileOwnerOrReadOnly]


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['post', 'status', 'author']
    search_fields = ['content', 'author__username', 'post__title']
    ordering_fields = ['created_at', 'updated_at']

    def get_queryset(self):
        queryset = Comment.objects.select_related('post', 'author')
        if self.request.user.is_staff:
            return queryset
        if self.request.user.is_authenticated:
            return queryset.filter(
                Q(status=Comment.ModerationStatus.APPROVED) | Q(author=self.request.user)
            ).distinct()
        return queryset.filter(status=Comment.ModerationStatus.APPROVED)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, *args, **kwargs):
        comment = self.get_object()
        comment.status = Comment.ModerationStatus.APPROVED
        comment.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(comment).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def reject(self, request, *args, **kwargs):
        comment = self.get_object()
        comment.status = Comment.ModerationStatus.REJECTED
        comment.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(comment).data)
