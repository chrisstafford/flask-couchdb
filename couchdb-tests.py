"""
couchdb-tests.py
================
This is a testing file for Flask-CouchDB. It should be run using Nose. It will
attempt to use the CouchDB server at ``http://localhost:5984/`` and the
database ``flaskext-test``. You can override these with the environment
variables `FLASKEXT_COUCHDB_SERVER` and `FLASKEXT_COUCHDB_DATABASE`.
"""

import os
import couchdb
import flask
import flaskext.couchdb
from couchdb.http import ResourceNotFound
from datetime import datetime

SERVER = os.environ.get('FLASKEXT_COUCHDB_SERVER', 'http://localhost:5984/')
DATABASE = os.environ.get('FLASKEXT_COUCHDB_DATABASE', 'flaskext-test')


class BlogPost(flaskext.couchdb.Document):
    title = flaskext.couchdb.TextField()
    text = flaskext.couchdb.TextField()
    author = flaskext.couchdb.TextField()
    tags = flaskext.couchdb.ListField(flaskext.couchdb.TextField())
    created = flaskext.couchdb.DateTimeField(default=datetime.now)
    
    by_author = flaskext.couchdb.ViewField('blog', '''\
    function (doc) {
        emit(doc.author, doc);
    }''')
    tagged = flaskext.couchdb.ViewField('blog', '''\
    function (doc) {
        doc.tags.forEach(function (tag) {
            emit(tag, doc);
        });
    }''')


SAMPLE_DATA = [
    dict(_id='a', username='steve', fullname='Steve Person', active=True),
    dict(_id='b', username='fred', fullname='Fred Person', active=True),
    dict(_id='c', username='joe', fullname='Joe Person', active=False)
]


SAMPLE_POSTS = [
    BlogPost(title='N1', text='number 1', author='Steve Person', id='1'),
    BlogPost(title='N2', text='number 2', author='Fred Person', id='2'),
    BlogPost(title='N3', text='number 3', author='Steve Person', id='3')
]


class TestFlaskextCouchDB(object):
    def setup(self):
        self.app = flask.Flask(__name__)
        self.app.debug = True
        self.app.config['COUCHDB_SERVER'] = SERVER
        self.app.config['COUCHDB_DATABASE'] = DATABASE
    
    def teardown(self):
        server = couchdb.Server(SERVER)
        try:
            server.delete(DATABASE)
        except ResourceNotFound:
            pass
    
    def test_g_couch(self):
        manager = flaskext.couchdb.CouchDBManager()
        manager.setup(self.app)
        print self.app.before_request_funcs, self.app.after_request_funcs
        with self.app.test_request_context('/'):
            self.app.preprocess_request()
            print dir(flask.g)
            assert hasattr(flask.g, 'couch')
            assert isinstance(flask.g.couch, couchdb.Database)
    
    def test_add_viewdef(self):
        manager = flaskext.couchdb.CouchDBManager()
        vd = flaskext.couchdb.ViewDefinition('tests', 'all', '''\
            function(doc) {
                emit(doc._id, null);
            }''')
        manager.add_viewdef(vd)
        assert vd in tuple(manager.all_viewdefs())
    
    def test_add_document(self):
        manager = flaskext.couchdb.CouchDBManager()
        manager.add_document(BlogPost)
        viewdefs = list(manager.all_viewdefs())
        viewdefs.sort(key=lambda d: d.name)
        assert viewdefs[0].name == 'by_author'
        assert viewdefs[1].name == 'tagged'
    
    def test_sync(self):
        manager = flaskext.couchdb.CouchDBManager()
        manager.add_document(BlogPost)
        server = couchdb.Server(SERVER)
        assert DATABASE not in server
        manager.sync(self.app)
        assert DATABASE in server
        db = server[DATABASE]
        assert '_design/blog' in db
        designdoc = db['_design/blog']
        assert 'by_author' in designdoc['views']
    
    def test_documents(self):
        manager = flaskext.couchdb.CouchDBManager()
        manager.setup(self.app)
        with self.app.test_request_context('/'):
            self.app.preprocess_request()
            post = BlogPost(title='Hello', text='Hello, world!',
                            author='Steve Person')
            post.id = 'hello'
            post.store()
            del post
            assert 'hello' in flask.g.couch
            post = BlogPost.load('hello')
            assert isinstance(post, BlogPost)
            assert post.id == 'hello'
            assert post.title == 'Hello'
    
    def test_loading_nonexistent(self):
        manager = flaskext.couchdb.CouchDBManager()
        manager.setup(self.app)
        with self.app.test_request_context('/'):
            self.app.preprocess_request()
            post = BlogPost.load('goodbye')
            assert post is None
    
    def test_running_document_views(self):
        manager = flaskext.couchdb.CouchDBManager()
        manager.add_document(BlogPost)
        manager.setup(self.app)
        manager.sync(self.app)
        with self.app.test_request_context('/'):
            self.app.preprocess_request()
            for post in SAMPLE_POSTS:
                post.store()
            steve_res = BlogPost.by_author['Steve Person']
            assert all(r.author == 'Steve Person' for r in steve_res)
    
    def test_running_standalone_views(self):
        manager = flaskext.couchdb.CouchDBManager()
        viewdef = flaskext.couchdb.ViewDefinition('tests', 'active', '''\
            function (doc) {
                if (doc.active) {
                    emit(doc.username, doc.fullname)
                };
            }''')
        manager.add_viewdef(viewdef)
        manager.setup(self.app)
        manager.sync(self.app)
        with self.app.test_request_context('/'):
            self.app.preprocess_request()
            for d in SAMPLE_DATA:
                flask.g.couch.save(d)
            results = tuple(viewdef())
            assert len(results) == 2
            goal = ['fred', 'steve']
            for row in results:
                if row.key not in goal:
                    assert False, '%s was not a key' % row.key
                goal.remove(row.key)
            assert not goal
    
    def test_autosync(self):
        track = []
        manager = flaskext.couchdb.CouchDBManager()
        manager.on_sync(lambda db: track.append('synced'))
        manager.setup(self.app)
        with self.app.test_request_context('/'):
            self.app.preprocess_request()
            assert 'synced' in track
    
    def test_manual_sync(self):
        track = []
        manager = flaskext.couchdb.CouchDBManager(auto_sync=False)
        manager.on_sync(lambda db: track.append('synced'))
        manager.setup(self.app)
        manager.sync(self.app)
        assert 'synced' in track
        track[:] = []   # clear track
        with self.app.test_request_context('/'):
            self.app.preprocess_request()
            assert 'synced' not in track
