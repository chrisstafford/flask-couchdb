# -*- coding: utf-8 -*-
"""
flaskext.couchdb
================
This module provides utilities to make using Flask with the CouchDB database
server easier.

:copyright: 2010 Matthew "LeafStorm" Frazier
:license:   MIT/X11, see LICENSE for details
"""

# needed to properly import the main CouchDB module
# wish they would have required absolute imports from the start
from __future__ import absolute_import
import couchdb
import couchdb.mapping as mapping
import itertools
from couchdb.design import ViewDefinition as OldViewDefinition
# easier than manually assigning them
from couchdb.mapping import (Field, TextField, FloatField, IntegerField,
                             LongField, BooleanField, DecimalField, DateField,
                             DateTimeField, TimeField, DictField, ListField,
                             Mapping, DEFAULT)
from flask import g, current_app

__all__ = ['CouchDBManager']
__all__.extend(mapping.__all__)


### The manager class

class CouchDBManager(object):
    """
    This manages connecting to the database every request and synchronizing
    the view definitions to it.
    
    :param auto_sync: Whether to automatically sync the database every
                      request. (Defaults to `True`.)
    """
    def __init__(self, auto_sync=True):
        self.auto_sync = auto_sync
        self.dc_viewdefs = {}
        self.general_viewdefs = []
        self.sync_callbacks = []
    
    def all_viewdefs(self):
        """
        This iterates through all the view definitions registered generally
        and the ones on specific document classes.
        """
        return itertools.chain(self.general_viewdefs,
                               *self.dc_viewdefs.itervalues())
    
    def add_document(self, dc):
        """
        This adds all the view definitions from a document class so they will
        be added to the database when it is synced.
        
        :param dc: The class to add. It should be a subclass of `Document`.
        """
        for name in dir(dc):
            viewdefs = []
            item = getattr(dc, name)
            if isinstance(item, OldViewDefinition):
                viewdefs.append(item)
            if viewdefs:
                self.dc_viewdefs[dc] = viewdefs
    
    def add_viewdef(self, viewdef):
        """
        This adds standalone view definitions (it should be a `ViewDefinition`
        instance or list thereof) to the manager. It will be added to the
        design document when it it is synced.
        
        :param viewdef: The view definition to add. It can also be a tuple or
                        list.
        """
        if isinstance(viewdef, OldViewDefinition):
            self.general_viewdefs.append(viewdef)
        else:
            self.general_viewdefs.extend(viewdef)
    
    def on_sync(self, fn):
        """
        This adds a callback to run when the database is synced. The callbacks
        are passed the live database (so they should use that instead of
        relying on the thread locals), and can do pretty much whatever they
        want. The design documents have already been synchronized. Callbacks
        are called in the order they are added, but you shouldn't rely on
        that.
        
        If you can reliably detect whether it is necessary, this may be a good
        place to add default data. However, the callbacks could theoretically
        be run on every request, so it is a bad idea to insert the default
        data every time.
        
        :param fn: The callback function to add.
        """
        self.sync_callbacks.append(fn)
    
    def connect_db(self, app):
        """
        This connects to the database for the given app. It presupposes that
        the database has already been synced, and as such an error will be
        raised if the database does not exist.
        
        :param app: The app to get the settings from.
        """
        server_url = app.config['COUCHDB_SERVER']
        db_name = app.config['COUCHDB_DATABASE']
        server = couchdb.Server(server_url)
        return server[db_name]
    
    def sync(self, app):
        """
        This syncs the database for the given app. It will first make sure the
        database exists, then synchronize all the views and run all the
        callbacks with the connected database.
        
        It will run any callbacks registered with `on_sync`, and when the
        views are being synchronized, if a method called `update_design_doc`
        exists on the manager, it will be called before every design document
        is updated.
        
        :param app: The application to synchronize with.
        """
        server_url = app.config['COUCHDB_SERVER']
        db_name = app.config['COUCHDB_DATABASE']
        server = couchdb.Server(server_url)
        if db_name not in server:
            db = server.create(db_name)
        else:
            db = server[db_name]
        OldViewDefinition.sync_many(
            db, tuple(self.all_viewdefs()),
            callback=getattr(self, 'update_design_doc', None)
        )
        for callback in self.sync_callbacks:
            callback(db)
    
    def setup(self, app):
        """
        This method sets up the request/response handlers needed to connect to
        the database on every request.
        
        :param app: The application to set up.
        """
        app.before_request(self.request_start)
        app.after_request(self.request_end)
    
    def request_start(self):
        if self.auto_sync and not current_app.config.get('DISABLE_AUTO_SYNC'):
            self.sync(current_app)
        g.couch = self.connect_db(current_app)
    
    def request_end(self, response):
        del g.couch
        print('database closed down')
        return response


### Jury-rigged CouchDB classes

class Document(mapping.Document):
    """
    This class can be used to represent a single "type" of document. You can
    use this to more conveniently represent a JSON structure as a Python
    object in the style of an object-relational mapper.
    
    You populate a class with instances of `Field` for all the attributes you
    want to use on the class.
    """
    @classmethod
    def load(cls, id, db=None):
        """
        This is used to retrieve a specific document from the database. If a
        database is not given, the thread-local database (``g.couch``) is
        used. 
        
        For compatibility with code used to the parameter ordering used in the
        original CouchDB, the parameters can be given in reverse order.
        
        :param id: The document ID to load.
        :param db: The database to use. Optional.
        """
        if isinstance(id, couchdb.Database):
            id, db = db, id
        return super(Document, cls).load(db or g.couch, id)
    
    def store(self, db=None):
        """
        This saves the document to the database. If a database is not given,
        the thread-local database (``g.couch``) is used.
        
        :param db: The database to use. Optional.
        """
        return mapping.Document.store(self, db or g.couch)


# just overridden to use the thread database

class ViewDefinition(OldViewDefinition):
    def __call__(self, db=None, **options):
        """
        This executes the view with the given database. If a database is not
        given, the thread-local database (``g.couch``) is used.
        
        :param db: The database to use, if necessary.
        :param options: Options to pass to the view.
        """
        return OldViewDefinition.__call__(self, db or g.couch, **options)
    
    def __getitem__(self, item):
        """
        Since it's possible to use this variant of `ViewDefinition` without
        an explicit database, this method is added for simplicity. For
        example, both sets of calls are equivalent::
        
            viewdef()['spam']
            viewdef['spam']
            
            viewdef()['eggs':'ham']
            viewdef['eggs':'ham']
        
        :param item: An item, or a slice.
        """


# only overridden so it will use our ViewDefinition
# this should be transparent to the user

class ViewField(mapping.ViewField):
    def __get__(self, instance, cls=None):
        wrapper = mapping.ViewField.__get__(self, instance, cls).wrapper
        return ViewDefinition(self.design, self.name, self.map_fun,
                              self.reduce_fun, language=self.language,
                              wrapper=wrapper, **self.defaults)
