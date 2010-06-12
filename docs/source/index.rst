=============
Flask-CouchDB
=============
.. currentmodule:: flaskext.couchdb

Flask-CouchDB makes it easy to use the powerful `CouchDB`_ database with
Flask.

.. _CouchDB: http://couchdb.apache.org/


Getting Started
===============
To get started, create an instance of the :class:`CouchDBManager` class. This
is used to set up the connection every request and ensure that your database
exists, design documents are synced, and the like. Then, you call its
:meth:`~CouchDBManager.setup` method with the app to register the necessary
handlers. ::

    manager = CouchDBManager()
    # ...add document types and view definitions...
    manager.setup(app)

The database to connect with is determined by the configuration. The
`COUCHDB_SERVER` application config value indicates the actual server to
connect to (for example, ``http://localhost:5984/``), and `COUCHDB_DATABASE`
indicates the database to use on the server (for example, ``webapp``).

By default, the database will be checked to see if it exists - and views will
be synchronized to their design documents - on every request. However, this
can (and maybe should) be customized - see `Database Sync Behavior
<syncing>`_ for more details.

Since the manager does not actually do anything until it is set up, it is safe
(and useful) for it to be created in advance, separately from the application
it is used with.


Basic Use
=========
On every request, the database is available as ``g.couch``. You will, of
course, want to check couchdb-python's documentation of the
:class:`couchdb.client.Database` class for more detailed instructions, but
some of the most useful methods are::

    # creating
    document = dict(title="Hello", content="Hello, world!")
    g.couch[some_id] = document
    
    # retrieving
    document = g.couch[some_id]     # raises error if it doesn't exist
    document = g.couch.get(some_id) # returns None if it doesn't exist
    
    # updating
    g.couch.save(document)

If you use this style of DB manipulation a lot, it might be useful to create
your own :class:`LocalProxy`, as some people (myself included) find the ``g.``
prefix annoying or unelegant. ::

    couch = LocalProxy(lambda: g.couch)

You can then use ``couch`` just like you would use ``g.couch``.


Writing Views
=============
If you register views with the `CouchDBManager`, they will be synchronized to
the database, so you can always be sure they can be called properly. They are
created with the `ViewDefinition` class.

View functions can have two parts - a map function and a reduce function. The
"map" function takes documents and emits any number of rows. Each row has a
key, a value, and the document ID that generated it. The "reduce" function
takes a list of keys, a list of values, and a parameter describing whether it
is in "rereduce" mode. It should return a value that reduces all the values
down into one single value. For maximum portability, most view functions are
written in JavaScript, though more view servers - including a Python one - can
be installed on the server.

The `ViewDefinition` class works like this::

    active_users_view = ViewDefinition('users', 'active', '''\
        function (doc) {
            if (doc.active) {
                emit(doc.username, doc)
            };
        }''')

``'users'`` is the design document this view is a part of, and ``'active'`` is
the name of the view. This particular view only has a map function. If you had
a reduce function, you would pass it after the map function::

    tag_counts_view = ViewDefinition('blog', 'tag_counts', '''\
        function (doc) {
            doc.tags.forEach(function (tag) {
                emit(tag, 1);
            });
        }''', '''\
        function (keys, values, rereduce) {
            return sum(values);
        }''', group=True)

The ``group=True`` is a default option. You can pass it when calling the view,
but since it causes only one row to be created for each unique key value, it
makes sense as the default for our view.

To get the results of a view, you can call its definition. Within a request,
it will automatically use ``g.couch``, but you can still pass in a value
explicitly. They return a `couchdb.client.ViewResults` object, which will
actually fetch the results once it is iterated over. You can also use getitem
and getslice notation to apply a range of keys. For example::

    active_users_view()     # rows for every active user
    active_users_view['a':'b']  # rows for every user between a and b
    tag_count()             # rows for every tag
    tag_count['flask']      # one row for just the 'flask' tag

To make sure that you can call the views, though, you need to add them to the
`CouchDBManager` with the `~CouchDBManager.add_viewdef` method. ::

    manager.add_viewdef((active_users_view, tag_count_view))

This does not cover writing views in detail. A good reference for writing
views is the `Introduction to CouchDB views`_ page on the CouchDB
wiki.

.. _Introduction to CouchDB views: http://wiki.apache.org/couchdb/Introduction_to_CouchDB_views


Mapping Documents to Objects
============================
With the `Document` class, you can map raw JSON objects to Python objects,
which can make it easier to work with your data. You create a document class
in a similar manner to ORMs such as Django, Elixir, and SQLObject. ::

    class BlogPost(Document):
        title = TextField()
        content = TextField()
        author = TextField()
        created = DateTimeField(default=datetime.datetime.now)
        tags = ListField(TextField())
        comments_allowed = BooleanField(default=True)

You can then create and edit documents just like you would a plain old object,
and then save them back to the database with the `~Document.store` method. ::

    post = BlogPost(title='Hello', content='Hello, world!', author='Steve')
    post.id = uuid.uuid4().hex
    post.store()

To retrieve a document, use the `~Document.load` method. It will return `None`
if the document with the given ID could not be found. ::

    post = BlogPost.load(some_id)
    if post is None:
        abort(404)
    return render_template(post=post)

Complex Fields
--------------
One advantage of using JSON objects is that you can include complex data
structures right in your document classes. For example, the ``tags`` field in
the example above uses a `ListField`::

    tags = ListField(TextField())

This lets you have a list of tags, as strings. You can also use `DictField`.
If you provide a mapping to the dict field (probably using the `Mapping.build`
method), it lets you have another, nested data structure, for example::

    author = DictField(Mapping.build(
        name=TextField(),
        email=TextField()
    ))

And you can use it just like it's a nested document::

    post.author.name = 'Steve Person'
    post.author.email = 'sperson@example.com'

On the other hand, if you use it with no mapping, it's just a plain old dict::

    metadata = DictField()

You can combine the two fields, as well. For example, if you wanted to include
comments on the post::

    comments = ListField(DictField(Mapping.build(
        text=TextField(),
        author=TextField(),
        approved=BooleanField(default=False),
        published=DateTimeField(default=datetime.datetime.now)
    )))


Adding Views
------------
The `ViewField` class can be used to add views to your document classes. You
create it just like you do a normal `ViewDefinition`, except you attach it to
the class and you don't have to give it a name, just a design document (it
will automatically take the name of its attribute)::

    tagged = ViewField('blog', '''\
        function (doc) {
            doc.tags.forEach (tag) {
                emit(tag, doc);
            };
        }''')

When you access it, either from the class or from an instance, it will return
a `ViewDefinition`, which you can call like normal. The results will
automatically be wrapped in the document class. ::

    BlogPost.tagged()           # a row for every tag on every document
    BlogPost.tagged['flask']    # a row for every document tagged 'flask'

.. note::
   
    If you use `ViewField`, please be aware that every value in the view
    **must** return a document that matches the document class's schema. But
    if you want to have some sort of other result from the view, there is
    nothing stopping you from attaching a plain old `ViewDefinition` to the
    class, like this::
    
        tag_counts = ViewDefinition('blog', 'tag_counts', '''\
            function (doc) {
                doc.tags.forEach(function (tag) {
                    emit(tag, 1);
                });
            }''', '''\
            function (keys, values, rereduce) {
                return sum(values);
            }''', group=True)
    
    In this case, however, you still have to give a name for the view, as the
    metaclass only automatically names actual `ViewField` instances.

To schedule all of the views on a document class for synchronization, use the
`CouchDBManager.add_document_class` method. All the views will be added when
the database syncs. ::

    manager.add_document_class(BlogPost)


.. _syncing:

Database Sync Behavior
======================
By default, the database is "synced" by a callback on every request. During
the sync:

- The manager checks whether the database exists, and if it does not, it
  creates it.
- All the view definitions registered on Document classes or just on their own
  are synchronized to their design documents.
- Any `~CouchDBManager.on_sync` callbacks are run.

The default behavior is intended to ensure a minimum of effort to get up and
running correctly. However, it is very inefficient, as a number of possibly
unnecessary HTTP requests may be made during the sync. As such, you can turn
automatic syncing off.

If you don't want to disable it at the code level, it can be disabled at the
configuration level. After you have run a single request, or synced manually,
you can set the `DISABLE_AUTO_SYNCING` config option to `True`. It will
prevent the database from syncing on every request, even if it is enabled in
the code.

A more prudent method is to pass the ``auto_sync=False`` option to
the :class:`CouchDBManager` constructor. This will prevent per-request syncing
even if it is not disabled in the config. Then, you can manually call the
:meth:`~CouchDBManager.sync` method (with an app) and it will sync at that
time. (You have to have set up the app before then, so it's best to put this
either in an app factory function or the server script - somewhere you can
guarantee the app has already been configured.) For example::

    app = Flask(__name__)
    # ...configure the app...
    manager.setup(app)
    manager.sync(app)


API Documentation
=================
This documentation is automatically generated from the sourcecode. This covers
the entire public API (i.e. everything that can be star-imported from
`flaskext.couchdb`). Some of these have been directly imported from the
original couchdb-python module.


The Manager
-----------
.. autoclass:: CouchDBManager
   :members:


View Definition
---------------
.. autoclass:: ViewDefinition
   :members:
   :inherited-members:
   

Documents
---------
.. autoclass:: Document
   :members:
   :inherited-members:

.. autoclass:: Field
   :members:

.. autoclass:: Mapping
   :members:


Field Types
-----------
.. autoclass:: TextField

.. autoclass:: IntegerField

.. autoclass:: FloatField

.. autoclass:: LongField

.. autoclass:: DecimalField

.. autoclass:: BooleanField

.. autoclass:: DateTimeField

.. autoclass:: DateField

.. autoclass:: TimeField

.. autoclass:: ListField

.. autoclass:: DictField


Additional Reference
====================
- For actually getting started with CouchDB and finding out if you want to use
  it, you should read the `official CouchDB Website`_.
- The `CouchDB wiki`_ is another good source of information on the CouchDB API
  and how to write views.
- Flask-CouchDB is based on the excellent `couchdb-python`_ library. Its
  documentation can help you understand what is really going on behind the
  the scenes.
- `CouchDB - The Definitive Guide`_ is a book published by O'Reilly and
  made freely available on its Web site. It doesn't cover developing with
  CouchDB using client libraries very much, but it contains a good amount
  of insight into how CouchDB works.

.. _official CouchDB Website: http://couchdb.apache.org/
.. _CouchDB wiki: http://wiki.apache.org/couchdb/
.. _couchdb-python: http://code.google.com/p/couchdb-python/
.. _CouchDB - The Definitive Guide: http://books.couchdb.org/relax/
