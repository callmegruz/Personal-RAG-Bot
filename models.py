from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

# Initialize the SQLAlchemy extension. The actual Flask app context will bind to it in app.py.
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    role = db.Column(db.String(20), nullable=False, default="user")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    conversations = db.relationship('Conversation', backref='user', cascade='all, delete-orphan')
    memories = db.relationship('UserMemory', backref='user', cascade='all, delete-orphan')

class Conversation(db.Model):
    __tablename__ = 'conversations'
    
    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    summary = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    messages = db.relationship('ChatMessage', backref='conversation', cascade='all, delete-orphan')

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class UserMemory(db.Model):
    __tablename__ = 'user_memories'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    fact_key = db.Column(db.String(100), nullable=False)
    fact_value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
