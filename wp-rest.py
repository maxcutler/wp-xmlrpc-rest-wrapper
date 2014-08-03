from datetime import timedelta

from flask import Flask, json, helpers, request
from flask.views import MethodView

from wordpress_xmlrpc import Client
from wordpress_xmlrpc import methods as wp_methods


app = Flask(__name__)
wp = Client('http://localhost/wptrunk/src/xmlrpc.php', 'maxcutler', 'maxcutler')

blog_time_zone = wp.call(wp_methods.options.GetOptions(['time_zone']))[0].value
tz_delta = timedelta(seconds = int(blog_time_zone) * 3600)

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
        endpoint = route_to_abs(helpers.url_for('posts', **endpoint_params))

        resources[name] = {
            'versions': {
                '1': endpoint,
                'latest': endpoint
            },
            'supports': ['GET', 'POST', 'DELETE'],
        }

    extra_resources = [
        (CommentApi.name, CommentCollectionApi.name),
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
                '1': endpoint,
                'latest': endpoint
            },
            'supports': ['GET', 'POST', 'DELETE']
        }

    response['resources'] = resources

    return json.jsonify(response)


class PostApi(MethodView):
    name = 'post'

    @staticmethod
    def from_xmlrpc(obj):
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
            'comment_status': obj.comment_status,
            'ping_status': obj.ping_status,
            'sticky': obj.sticky,
            'date_gmt': obj.date.isoformat(),
            'modified_gmt': obj.date_modified.isoformat(),
            'terms': map(TaxonomyTermApi.from_xmlrpc, obj.terms),
            'metadata': obj.custom_fields
        }

    def get(self):
        return 'get_post'


class PostCollectionApi(MethodView):
    name = 'posts'

    def get(self):
        page = int(request.values.get('page', 1))
        post_type = request.values.get('post_type', 'post')

        posts = wp.call(wp_methods.posts.GetPosts({
            'number': 20,
            'offset': (page - 1) * 20,
            'post_type': post_type
        }))

        response = {}
        response['items'] = map(PostApi.from_xmlrpc, posts)

        meta = {
            'supports': ['GET', 'POST']
        }

        paging_params = {}
        if (post_type != 'post'):
            paging_params['post_type'] = post_type

        if len(posts) == 20:
            meta['next'] = route_to_abs(helpers.url_for('posts', page=page+1, **paging_params))

        if page > 1:
            params = {}
            if (page > 2):
                params['page'] = page + 1
            meta['prev'] = route_to_abs(helpers.url_for('posts', **dict(paging_params, **params)))

        response['_meta'] = meta

        return json.jsonify(response)


class CommentApi(MethodView):
    name = 'comment'
    def get(self):
        return 'get_comment'


class CommentCollectionApi(MethodView):
    name = 'comments'
    def get(self):
        return 'get_comments'


class UserApi(MethodView):
    name = 'user'
    def get(self):
        return 'get_user'


class UserCollectionApi(MethodView):
    name = 'users'
    def get(self):
        return 'get_users'


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
    def get(self):
        return 'get_taxonomy'


class TaxonomyCollectionApi(MethodView):
    name = 'taxonomies'
    def get(self):
        return 'get_taxonomies'


class TaxonomyTermApi(MethodView):
    name = 'term'

    @staticmethod
    def from_xmlrpc(obj):
        term = {
            'id': obj.id,
            'name': obj.name,
            'slug': obj.slug,
            'description': obj.description,
            'count': obj.count,
            'taxonomy': {
                'self': route_to_abs(helpers.url_for(TaxonomyApi.name, id=obj.taxonomy)),
                'name': obj.taxonomy
            },
            '_meta': {
                'supports': ['GET', 'PUT', 'DELETE'],
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

    def get(self, taxonomy):
        return 'get_term'


class TaxonomyTermCollectionApi(MethodView):
    name = 'terms'

    def get(self, taxonomy):
        return 'get_terms'


def register_collection(collection, item):
    collection_pattern = '/wporg/1/' + collection.name + '/'
    app.add_url_rule(collection_pattern, view_func=collection.as_view(collection.name))
    app.add_url_rule(collection_pattern + '<id>/', view_func=item.as_view(item.name))


def register_nested_collection(parent, collection, item):
    parent_path = '/wporg/1/' + parent.name + '/' + '<parent_id>/'
    collection_path = parent_path + collection.name + '/'
    app.add_url_rule(collection_path, view_func=collection.as_view(collection.name))
    app.add_url_rule(collection_path + '<id>/', view_func=item.as_view(item.name))


register_collection(PostCollectionApi, PostApi)
register_collection(CommentCollectionApi, CommentApi)
register_collection(UserCollectionApi, UserApi)
register_collection(FileCollectionApi, FileApi)
register_collection(ImageCollectionApi, ImageApi)
register_collection(VideoCollectionApi, VideoApi)
register_collection(AudioCollectionApi, AudioApi)
register_collection(TaxonomyCollectionApi, TaxonomyApi)
register_nested_collection(TaxonomyCollectionApi, TaxonomyTermCollectionApi, TaxonomyTermApi)

if __name__ == '__main__':
    app.run(debug=True)