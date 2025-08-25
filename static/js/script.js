{% extends "base.html" %}

{% block content %}
<div class="hero-section">
    <div class="card">
        <div class="card-header">
            <h2 class="card-title"><i class="fas fa-key"></i> Login to CardCheck Pro</h2>
        </div>
        <div class="card-body">
            <form action="{{ url_for('login') }}" method="POST">
                <div class="form-group">
                    <label class="form-label" for="user_id">User ID</label>
                    <input type="text" class="form-input" id="user_id" name="user_id" placeholder="Enter your User ID" required>
                </div>
                <div class="form-group">
                    <label class="form-label" for="first_name">First Name</label>
                    <input type="text" class="form-input" id="first_name" name="first_name" placeholder="Enter your first name">
                </div>
                <button type="submit" class="btn btn-primary" style="width: 100%;">
                    <i class="fas fa-sign-in-alt"></i> Login
                </button>
            </form>
            <p style="margin-top: 16px; text-align: center; color: var(--chrome-text-light);">
                Don't have an account? You'll be registered automatically on first login.
            </p>
        </div>
    </div>
</div>
{% endblock %}