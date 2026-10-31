from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Category, Comment, Like, Post, Profile, Tag

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Profile
        fields = [
            'id', 'username', 'email', 'bio', 'avatar_url', 'website_url',
            'github_url', 'linkedin_url', 'updated_at',
        ]
        read_only_fields = ['id', 'username', 'email', 'updated_at']

    def validate_bio(self, value):
        return value.strip()


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['name', 'slug']
        read_only_fields = ['slug']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['name', 'slug', 'description']
        read_only_fields = ['slug']


class PostSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source='author.username', read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    categories = CategorySerializer(many=True, read_only=True)
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=50), write_only=True, required=False
    )
    category_names = serializers.ListField(
        child=serializers.CharField(max_length=80), write_only=True, required=False
    )
    url = serializers.HyperlinkedIdentityField(view_name='post-detail', lookup_field='slug')
    likes_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'url', 'title', 'slug', 'excerpt', 'content', 'cover_image_url',
            'author', 'tags', 'tag_names', 'categories', 'category_names', 'status', 'published_at',
            'view_count', 'is_featured',
            'likes_count', 'is_liked',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['slug', 'view_count', 'created_at', 'updated_at']

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        return bool(request and request.user.is_authenticated and Like.objects.filter(
            post=obj, user=request.user
        ).exists())

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Title cannot be blank.')
        return value

    def validate_excerpt(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Excerpt cannot be blank.')
        return value

    def validate_content(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Content cannot be blank.')
        return value

    def validate(self, attrs):
        status = attrs.get('status', getattr(self.instance, 'status', Post.Status.DRAFT))
        published_at = attrs.get('published_at', getattr(self.instance, 'published_at', None))
        is_featured = attrs.get('is_featured', getattr(self.instance, 'is_featured', False))
        if status == Post.Status.PUBLISHED and not published_at:
            raise serializers.ValidationError({
                'published_at': 'Published posts must have a publication date.'
            })
        if is_featured and status != Post.Status.PUBLISHED:
            raise serializers.ValidationError({
                'is_featured': 'Only published posts can be featured.'
            })
        request = self.context.get('request')
        if 'is_featured' in attrs and (not request or not request.user.is_staff):
            raise serializers.ValidationError({
                'is_featured': 'Only staff users can feature posts.'
            })
        return attrs

    def create(self, validated_data):
        tag_names = validated_data.pop('tag_names', [])
        category_names = validated_data.pop('category_names', [])
        post = super().create(validated_data)
        self._set_tags(post, tag_names)
        self._set_categories(post, category_names)
        return post

    def update(self, instance, validated_data):
        tag_names = validated_data.pop('tag_names', None)
        category_names = validated_data.pop('category_names', None)
        post = super().update(instance, validated_data)
        if tag_names is not None:
            self._set_tags(post, tag_names)
        if category_names is not None:
            self._set_categories(post, category_names)
        return post

    @staticmethod
    def _set_tags(post, tag_names):
        tags = [Tag.objects.get_or_create(name=name.strip())[0] for name in tag_names if name.strip()]
        post.tags.set(tags)

    @staticmethod
    def _set_categories(post, category_names):
        categories = [
            Category.objects.get_or_create(name=name.strip())[0]
            for name in category_names if name.strip()
        ]
        post.categories.set(categories)


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source='author.username', read_only=True)
    post_title = serializers.CharField(source='post.title', read_only=True)
    post = serializers.PrimaryKeyRelatedField(
        queryset=Post.objects.filter(status=Post.Status.PUBLISHED)
    )

    class Meta:
        model = Comment
        fields = ['id', 'post', 'post_title', 'author', 'content', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'post_title', 'status', 'created_at', 'updated_at']

    def validate_content(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Comment cannot be blank.')
        return value
