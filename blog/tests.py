from django.contrib.auth import get_user_model
from datetime import timedelta
import json
import logging
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Comment, Like, Post, Profile
from .logging import JsonFormatter


class PostApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='author', password='test-pass')
        self.post = Post.objects.create(
            title='Django APIs that scale',
            excerpt='A practical guide.',
            content='Use serializers, indexes, and tests.',
            author=self.user,
            status=Post.Status.PUBLISHED,
            published_at=timezone.now(),
        )

    def test_public_list_only_returns_published_posts(self):
        Post.objects.create(
            title='Draft architecture notes', excerpt='Private', content='Draft', author=self.user
        )
        response = self.client.get(reverse('post-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['slug'], self.post.slug)
        self.assertEqual(response.data['results'][0]['view_count'], 0)

    def test_allowed_frontend_origin_receives_cors_header(self):
        response = self.client.get(
            reverse('post-list'), HTTP_ORIGIN='http://localhost:3000'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers['Access-Control-Allow-Origin'], 'http://localhost:3000'
        )

    def test_requests_return_a_traceable_id_and_emit_structured_logs(self):
        with self.assertLogs('blog.request', level='INFO') as captured:
            response = self.client.get(reverse('post-list'), HTTP_X_REQUEST_ID='request-123')
        self.assertEqual(response.headers['X-Request-ID'], 'request-123')
        self.assertIn('request.complete', captured.output[-1])

        record = logging.LogRecord(
            'blog.request', logging.INFO, __file__, 0, 'request.complete', (), None
        )
        record.request_id = 'request-123'
        record.method = 'GET'
        record.path = '/api/posts/'
        record.status_code = 200
        record.duration_ms = 1.25
        event = json.loads(JsonFormatter().format(record))
        self.assertEqual(event['message'], 'request.complete')
        self.assertEqual(event['request_id'], 'request-123')
        self.assertEqual(event['status_code'], 200)
        self.assertEqual(event['duration_ms'], 1.25)

    def test_scheduled_and_archived_posts_are_hidden_from_public_readers(self):
        Post.objects.create(
            title='Scheduled post', excerpt='Later', content='Not live yet', author=self.user,
            status=Post.Status.PUBLISHED, published_at=timezone.now() + timedelta(days=1),
        )
        Post.objects.create(
            title='Archived post', excerpt='Old', content='No longer live', author=self.user,
            status=Post.Status.ARCHIVED,
        )
        response = self.client.get(reverse('post-list'))
        self.assertEqual(response.data['count'], 1)

    def test_featured_endpoint_only_returns_published_featured_posts(self):
        staff = get_user_model().objects.create_user(
            username='editor', password='test-pass', is_staff=True
        )
        self.client.force_authenticate(user=staff)
        response = self.client.patch(
            reverse('post-detail', kwargs={'slug': self.post.slug}),
            {'is_featured': True}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('post-featured'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_draft_preview_is_private_to_author_or_staff(self):
        draft = Post.objects.create(
            title='Private draft', excerpt='Preview', content='Work in progress', author=self.user
        )
        other_user = get_user_model().objects.create_user(username='other', password='test-pass')
        self.client.force_authenticate(user=other_user)
        response = self.client.get(reverse('post-preview', kwargs={'slug': draft.slug}))
        self.assertEqual(response.status_code, 404)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('post-preview', kwargs={'slug': draft.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Private draft')

    def test_authors_cannot_feature_posts_or_change_ownership(self):
        other_user = get_user_model().objects.create_user(username='other', password='test-pass')
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            reverse('post-detail', kwargs={'slug': self.post.slug}),
            {'is_featured': True, 'author': other_user.pk}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_featured)
        self.assertEqual(self.post.author_id, self.user.pk)

    def test_detail_view_increments_view_count_atomically(self):
        url = reverse('post-detail', kwargs={'slug': self.post.slug})
        first_response = self.client.get(url)
        second_response = self.client.get(url)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.data['view_count'], 1)
        self.assertEqual(second_response.data['view_count'], 2)

    def test_authenticated_user_can_like_and_unlike_once(self):
        url = reverse('post-like', kwargs={'slug': self.post.slug})
        self.client.force_authenticate(user=self.user)

        first_like = self.client.post(url)
        second_like = self.client.post(url)
        self.assertEqual(first_like.status_code, 201)
        self.assertEqual(second_like.status_code, 200)
        self.assertEqual(second_like.data['likes_count'], 1)
        self.assertTrue(second_like.data['liked'])
        self.assertEqual(Like.objects.filter(post=self.post, user=self.user).count(), 1)

        unlike = self.client.delete(url)
        self.assertEqual(unlike.status_code, 200)
        self.assertEqual(unlike.data['likes_count'], 0)
        self.assertFalse(unlike.data['liked'])

    def test_user_can_register_and_obtain_jwt_tokens(self):
        registration = self.client.post(reverse('register'), {
            'username': 'new-reader',
            'email': 'reader@example.com',
            'password': 'A-strong-password-123',
        }, format='json')
        self.assertEqual(registration.status_code, 201)

        token_response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'new-reader',
            'password': 'A-strong-password-123',
        }, format='json')
        self.assertEqual(token_response.status_code, 200)
        self.assertIn('access', token_response.data)
        self.assertIn('refresh', token_response.data)
        self.assertTrue(Profile.objects.filter(user__username='new-reader').exists())

    def test_profile_is_public_but_only_owner_can_update(self):
        profile = Profile.objects.get(user=self.user)
        response = self.client.get(reverse('profile-detail', kwargs={'pk': profile.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'author')

        other_user = get_user_model().objects.create_user(username='other', password='test-pass')
        self.client.force_authenticate(user=other_user)
        response = self.client.patch(
            reverse('profile-detail', kwargs={'pk': profile.pk}), {'bio': 'Not my profile'}, format='json'
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            reverse('profile-detail', kwargs={'pk': profile.pk}),
            {'bio': ' Backend developer '},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['bio'], 'Backend developer')

    def test_registration_rejects_weak_passwords(self):
        response = self.client.post(reverse('register'), {
            'username': 'weak-user',
            'email': 'weak@example.com',
            'password': 'password',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data['error']['details'])

    def test_authenticated_author_can_create_a_post(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse('post-list'), {
            'title': 'Testing Django services',
            'excerpt': 'Testing matters.',
            'content': 'Write focused API tests.',
            'status': 'draft',
            'tag_names': ['Django', 'Testing'],
            'category_names': ['Backend'],
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['author'], 'author')
        self.assertEqual(response.data['tags'][0]['name'], 'Django')
        self.assertEqual(response.data['categories'][0]['name'], 'Backend')

    def test_author_can_read_their_own_draft(self):
        draft = Post.objects.create(
            title='Draft architecture notes', excerpt='Private', content='Draft', author=self.user
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('post-detail', kwargs={'slug': draft.slug}))
        self.assertEqual(response.status_code, 200)

    def test_comment_requires_authentication_and_is_moderated(self):
        url = reverse('comment-list')
        response = self.client.post(url, {'post': self.post.pk, 'content': 'Great article!'}, format='json')
        self.assertIn(response.status_code, (401, 403))

        self.client.force_authenticate(user=self.user)
        response = self.client.post(url, {'post': self.post.pk, 'content': 'Great article!'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], Comment.ModerationStatus.PENDING)

    def test_only_staff_can_moderate_comments(self):
        comment = Comment.objects.create(post=self.post, author=self.user, content='Needs review')
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse('comment-approve', kwargs={'pk': comment.pk}))
        self.assertEqual(response.status_code, 403)

        staff = get_user_model().objects.create_user(
            username='moderator', password='test-pass', is_staff=True
        )
        self.client.force_authenticate(user=staff)
        response = self.client.post(reverse('comment-approve', kwargs={'pk': comment.pk}))
        self.assertEqual(response.status_code, 200)
        comment.refresh_from_db()
        self.assertEqual(comment.status, Comment.ModerationStatus.APPROVED)

    def test_post_validation_rejects_unpublished_published_posts_and_blank_text(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse('post-list'), {
            'title': 'Needs a date', 'excerpt': 'Valid excerpt', 'content': 'Valid content',
            'status': Post.Status.PUBLISHED,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error']['code'], 'validation_error')
        self.assertIn('published_at', response.data['error']['details'])

        response = self.client.post(reverse('post-list'), {
            'title': '   ', 'excerpt': 'Valid excerpt', 'content': 'Valid content',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('title', response.data['error']['details'])

    def test_comment_validation_rejects_whitespace_only_content(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse('comment-list'), {
            'post': self.post.pk, 'content': '   ',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('content', response.data['error']['details'])

    def test_errors_use_a_standard_response_shape(self):
        response = self.client.get(reverse('post-detail', kwargs={'slug': 'does-not-exist'}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(set(response.data.keys()), {'error'})
        self.assertEqual(response.data['error']['code'], 'not_found')
        self.assertIn('message', response.data['error'])
        self.assertIn('details', response.data['error'])

    def test_public_readers_only_see_approved_comments(self):
        Comment.objects.create(post=self.post, author=self.user, content='Pending comment')
        Comment.objects.create(
            post=self.post, author=self.user, content='Approved comment',
            status=Comment.ModerationStatus.APPROVED,
        )
        response = self.client.get(reverse('comment-list'), {'post': self.post.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['content'], 'Approved comment')
