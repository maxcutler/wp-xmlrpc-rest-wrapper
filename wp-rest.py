from datetime import timedelta

from flask import Flask, json, helpers, request
from flask.views import MethodView

from wordpress_xmlrpc import Client
from wordpress_xmlrpc import methods as wp_methods
from wordpress_xmlrpc.methods import taxonomies as wp_taxonomies


app = Flask(__name__)
wp = Client('http://localhost/wptrunk/src/xmlrpc.php', 'maxcutler', 'maxcutler')

blog_time_zone = wp.call(wp_methods.options.GetOptions(['time_zone']))[0].value
tz_delta = timedelta(seconds = int(blog_time_zone) * 3600)

default_page_size = 10

def route_to_abs(route):
    return request.url_root + route[1:]


@app.route('/')
def api_route():
    response = {}

    option_map = {
        'blog_title': 'name',
        'blog_tagline': 'description',
        'home_url': 'URL',
    }
    options = wp.call(wp_methods.options.GetOptions(option_map.keys()))
    for option in options:
        key = option_map.get(option.name, None)
        if key:
            response[key] = option.value

    resources = {}

    post_types = wp.call(wp_methods.posts.GetPostTypes())
    for name, post_type in post_types.items():
        if name == 'attachment':
            continue

        endpoint_params = {}
        if (name != 'post'):
            endpoint_params['post_type'] = name
        endpoint = route_to_abs(helpers.url_for(PostCollectionApi.name, **endpoint_params))

        resources[name] = {
            'versions': {
                'v1': endpoint,
                'latest': endpoint
            },
            'supports': ['GET', 'POST', 'DELETE'],
        }

    extra_resources = [
        (UserApi.name, UserCollectionApi.name),
        (FileApi.name, FileCollectionApi.name),
        (ImageApi.name, ImageCollectionApi.name),
        (VideoApi.name, VideoCollectionApi.name),
        (AudioApi.name, AudioCollectionApi.name),
        (TaxonomyApi.name, TaxonomyCollectionApi.name)
    ]

    for singular, plural in extra_resources:
        endpoint = route_to_abs(helpers.url_for(plural))
        resources[singular] = {
            'versions': {
                'v1': endpoint,
                'latest': endpoint
            },
            'supports': ['GET', 'POST', 'DELETE']
        }

    response['resources'] = resources

    return json.jsonify(response)


class PostApi(MethodView):
    name = 'post'
    media_type = 'application/vnd.wordpress.post.v1'

    @staticmethod
    def from_xmlrpc_custom_field(field):
        return {
            'id': field['id'],
            'key': field['key'],
            'value': field['value'],
            '_meta': {
                'links': {
                    'self': '',
                },
                'supports': ['GET', 'PUT', 'DELETE']
            }
        }

    @staticmethod
    def from_xmlrpc(obj):
        author = None
        if (obj.user):
            author = UserApi.from_xmlrpc(wp.call(wp_methods.users.GetUser(obj.user)))

        return {
            'id': obj.id,
            'title': obj.title,
            'status': obj.post_status,
            'type': obj.post_type,
            'link': obj.link,
            'date': (obj.date + tz_delta).isoformat(),
            'modified': (obj.date_modified + tz_delta).isoformat(),
            'format': obj.post_format,
            'slug': obj.slug,
            'guid': obj.guid,
            'excerpt': {
                'raw': obj.excerpt
            },
            'content': {
                'raw': obj.content
            },
            'author': author,
            'comment_status': obj.comment_status,
            'ping_status': obj.ping_status,
            'sticky': obj.sticky,
            'date_gmt': obj.date.isoformat(),
            'modified_gmt': obj.date_modified.isoformat(),
            'terms': map(TaxonomyTermApi.from_xmlrpc, obj.terms),
            'metadata': map(PostApi.from_xmlrpc_custom_field, obj.custom_fields),
            '_meta': {
                'links': {
                    'self': route_to_abs(helpers.url_for(PostApi.name, id=obj.id)),
                    'comments': route_to_abs(helpers.url_for(CommentCollectionApi.name, parent_id=obj.id))
                },
                'supports': ['GET', 'PUT', 'DELETE'],
                'media_type': PostApi.media_type
            }
        }

    def get(self, id):
        post = wp.call(wp_methods.posts.GetPost(id))
        return json.jsonify(PostApi.from_xmlrpc(post))


class PostCollectionApi(MethodView):
    name = 'posts'

    def get(self):
        page = int(request.values.get('page', 1))
        post_type = request.values.get('post_type', 'post')

        posts = wp.call(wp_methods.posts.GetPosts({
            'number': default_page_size,
            'offset': (page - 1) * default_page_size,
            'post_type': post_type
        }))

        response = {}
        response['items'] = map(PostApi.from_xmlrpc, posts)

        meta = {
            'supports': ['GET', 'POST']
        }

        links = {}

        paging_params = {}
        if (post_type != 'post'):
            paging_params['post_type'] = post_type

        if len(posts) == default_page_size:
            links['next'] = route_to_abs(helpers.url_for(PostCollectionApi.name, page=page+1, **paging_params))

        if page > 1:
            params = {}
            if (page > 2):
                params['page'] = page + 1
            links['prev'] = route_to_abs(helpers.url_for(PostCollectionApi.name, **dict(paging_params, **params)))

        meta['links'] = links
        response['_meta'] = meta

        return json.jsonify(response)


class CommentApi(MethodView):
    name = 'comment'
    media_type = 'application/vnd.wordpress.comment.v1'

    @staticmethod
    def from_xmlrpc(obj):
        return {
            '_meta': {
                'media_type': CommentApi.media_type,
                'supports': ['GET', 'PUT', 'DELETE'],
                'links': {
                    'self': route_to_abs(helpers.url_for(CommentApi.name, parent_id=obj.post, id=obj.id))
                }
            },
            'id': obj.id,
            'date': obj.date_created.isoformat(),
            'status': obj.status,
            'content': obj.content,
            'link': obj.link,
            'author': obj.author,
            'author_url': obj.author_url,
            'author_email': obj.author_email,
            'author_ip': obj.author_ip
        }

    def get(self, parent_id, id):
        comment = wp.call(wp_methods.comments.GetComment(id))
        return json.jsonify(CommentApi.from_xmlrpc(comment))


class CommentCollectionApi(MethodView):
    name = 'comments'

    def get(self, parent_id):
        response = {}

        page = int(request.values.get('page', 1))
        comments = wp.call(wp_methods.comments.GetComments({
            'post_id': parent_id,
            'number': default_page_size,
            'offset': (page - 1) * default_page_size
        }))

        response['items'] = map(CommentApi.from_xmlrpc, comments)
        response['_meta'] = {
            'supports': ['GET', 'POST'],
            'links': {
                'self': route_to_abs(helpers.url_for(CommentCollectionApi.name, parent_id=parent_id)),
                'parent': route_to_abs(helpers.url_for(PostApi.name, id=parent_id))
            }
        }

        return json.jsonify(response)


class UserApi(MethodView):
    name = 'user'
    media_type = 'application/vnd.wordpress.user.v1'

    @staticmethod
    def from_xmlrpc(obj):
        return {
            '_meta': {
                'media_type': UserApi.media_type,
                'supports': ['GET'],
                'links': {
                    'self': route_to_abs(helpers.url_for(UserApi.name, id=obj.id))
                }
            },
            'id': obj.id,
            'username': obj.username,
            'nickname': obj.nickname,
            'description': obj.bio,
            'email': obj.email,
            'url': obj.url
        }

    def get(self, id):
        user = wp.call(wp_methods.users.GetUser(id))
        return json.jsonify(UserApi.from_xmlrpc(user))


class UserCollectionApi(MethodView):
    name = 'users'

    def get(self):
        page = int(request.values.get('page', 1))
        users = wp.call(wp_methods.users.GetUsers({
            'number': default_page_size,
            'offset': (page - 1) * default_page_size
        }))

        response = {}
        response['items'] = map(UserApi.from_xmlrpc, users)
        response['_meta'] = {
            'supports': ['GET']
        }

        return json.jsonify(response)


class FileApi(MethodView):
    name = 'file'
    def get(self):
        return 'get_file'


class FileCollectionApi(MethodView):
    name = 'files'
    def get(self):
        return 'get_files'


class ImageApi(MethodView):
    name = 'image'
    def get(self):
        return 'get_image'


class ImageCollectionApi(MethodView):
    name = 'images'
    def get(self):
        return 'get_images'


class VideoApi(MethodView):
    name = 'video'
    def get(self):
        return 'get_video'


class VideoCollectionApi(MethodView):
    name = 'videos'
    def get(self):
        return 'get_videos'


class AudioApi(MethodView):
    name = 'audio_item'
    def get(self):
        return 'get_audio'


class AudioCollectionApi(MethodView):
    name = 'audio'
    def get(self):
        return 'get_audio'


class TaxonomyApi(MethodView):
    name = 'taxonomy'
    media_type = 'application/vnd.wordpress.taxonomy.v1'

    @staticmethod
    def from_xmlrpc(obj):
        return {
            'name': obj.name,
            'label': obj.label,
            'hierarchical': obj.hierarchical,
            'public': obj.public,
            'show_ui': obj.show_ui,
            'is_builtin': obj.is_builtin,
            'object_types': obj.object_type,
            '_meta': {
                'supports': ['GET'],
                'media_type': TaxonomyApi.media_type,
                'links': {
                    'self': route_to_abs(helpers.url_for(TaxonomyApi.name, id=obj.name)),
                    'terms': route_to_abs(helpers.url_for(TaxonomyTermCollectionApi.name, parent_id=obj.name))
                }
            }
        }

    def get(self, id):
        taxonomy = wp.call(wp_taxonomies.GetTaxonomy(id))
        return json.jsonify(TaxonomyApi.from_xmlrpc(taxonomy))


class TaxonomyCollectionApi(MethodView):
    name = 'taxonomies'

    def get(self):
        taxonomies = wp.call(wp_taxonomies.GetTaxonomies())

        response = {}
        response['items'] = map(TaxonomyApi.from_xmlrpc, taxonomies)
        response['_meta'] = {
            'supports': ['GET']
        }

        return json.jsonify(response)


class TaxonomyTermApi(MethodView):
    name = 'term'
    media_type = 'application/vnd.wordpress.taxonomyterm.v1'

    @staticmethod
    def from_xmlrpc(obj):
        term = {
            'id': obj.id,
            'name': obj.name,
            'slug': obj.slug,
            'description': obj.description,
            'count': obj.count,
            'taxonomy': {
                '_meta': {
                    'links': {
                        'self': route_to_abs(helpers.url_for(TaxonomyApi.name, id=obj.taxonomy)),
                    },
                    'media_type': TaxonomyApi.media_type,
                    'supports': ['GET']
                },
                'name': obj.taxonomy
            },
            '_meta': {
                'supports': ['GET', 'PUT', 'DELETE'],
                'media_type': TaxonomyTermApi.media_type,
                'links': {
                    'self': route_to_abs(helpers.url_for(TaxonomyTermApi.name, parent_id=obj.taxonomy, id=obj.id))
                }
            }
        }

        if obj.parent and int(obj.parent) > 0:
            term['parent'] = {
                'id': obj.parent,
                'self': route_to_abs(helpers.url_for(TaxonomyTermApi.name, parent_id=obj.taxonomy, id=obj.parent))
            }

        return term

    def get(self, parent_id, id):
        term = wp.call(wp_taxonomies.GetTerm(parent_id, id))
        return json.jsonify(TaxonomyTermApi.from_xmlrpc(term))


class TaxonomyTermCollectionApi(MethodView):
    name = 'terms'

    def get(self, parent_id):
        page = int(request.values.get('page', 1))

        terms = wp.call(wp_taxonomies.GetTerms(parent_id, {
            'number': default_page_size,
            'offset': (page - 1) * default_page_size
        }))

        response = {}
        response['items'] = map(TaxonomyTermApi.from_xmlrpc, terms)
        response['_meta'] = {
            'supports': ['GET', 'POST']
        }

        return json.jsonify(response)


def register_collection(collection, item):
    collection_pattern = '/wporg/v1/' + collection.name + '/'
    app.add_url_rule(collection_pattern, view_func=collection.as_view(collection.name))
    app.add_url_rule(collection_pattern + '<id>/', view_func=item.as_view(item.name))


def register_nested_collection(parent, collection, item):
    parent_path = '/wporg/v1/' + parent.name + '/' + '<parent_id>/'
    collection_path = parent_path + collection.name + '/'
    app.add_url_rule(collection_path, view_func=collection.as_view(collection.name))
    app.add_url_rule(collection_path + '<id>/', view_func=item.as_view(item.name))


register_collection(PostCollectionApi, PostApi)
register_nested_collection(PostCollectionApi, CommentCollectionApi, CommentApi)
register_collection(UserCollectionApi, UserApi)
register_collection(FileCollectionApi, FileApi)
register_collection(ImageCollectionApi, ImageApi)
register_collection(VideoCollectionApi, VideoApi)
register_collection(AudioCollectionApi, AudioApi)
register_collection(TaxonomyCollectionApi, TaxonomyApi)
register_nested_collection(TaxonomyCollectionApi, TaxonomyTermCollectionApi, TaxonomyTermApi)

if __name__ == '__main__':
    app.run(debug=True)