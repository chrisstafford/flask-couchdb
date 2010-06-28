# -*- coding: utf-8 -*-
"""
example/guestbook.py
====================
This is an example application for Flask-CouchDB. It's a simple guestbook that
people can sign.

:copyright: 2010 Matthew "LeafStorm" Frazier
:license:   MIT/X11, see LICENSE for details (part of Flask-CouchDB)
"""
import datetime
from flask import Flask, render_template, flash, request, redirect, url_for
from flaskext.couchdb import (CouchDBManager, Document, TextField,
                              DateTimeField, ViewField, paginate)


# application setup
app = Flask(__name__)


# config
COUCHDB_SERVER = 'http://localhost:5984/'
COUCHDB_DATABASE = 'example-guestbook'
SECRET_KEY = 'set this to something secret'

app.config.from_object(__name__)


# model
class Signature(Document):
    doc_type = 'signature'
    
    message = TextField()
    author = TextField()
    time = DateTimeField(default=datetime.datetime.now)
    
    all = ViewField('guestbook', '''
        function (doc) {
            if (doc.doc_type == 'signature') {
                emit(doc.time, doc);
            };
        }''', descending=True)


manager = CouchDBManager()
manager.add_document(Signature)
manager.setup(app)


# views
@app.route('/')
def display():
    page = paginate(Signature.all(), 5, request.args.get('start'))
    return render_template('display.html', page=page)


@app.route('/', methods=['POST'])
def post():
    message = request.form.get('message')
    author = request.form.get('author')
    if not message or not author:
        flash("You must fill in both a message and an author")
    else:
        signature = Signature(message=message, author=author)
        signature.store()
        flash("Signature stored")
    return redirect(url_for('display'))


if __name__ == '__main__':
    app.config.from_envvar('GUESTBOOK_SETTINGS', silent=True)
    app.run(debug=True)
