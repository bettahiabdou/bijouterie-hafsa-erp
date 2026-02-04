# Bijouterie Hafsa ERP - Authentication & Login Setup

## 🔐 Overview

The complete authentication and user management system is now ready for use. The system includes:

- **Login/Logout functionality**
- **User profile management**
- **Password change system**
- **Activity logging & audit trail**
- **Admin user management**
- **Role-based access control**

---

## 🚀 Quick Start

### 1. Create Admin User

```bash
cd /Users/user/.claude-worktrees/Claude_cde/serene-gagarin
source venv/bin/activate
python manage.py createsuperuser
```

Follow the prompts to create:
- **Username**: (e.g., `admin`)
- **Email**: (e.g., `admin@bijouterie.local`)
- **Password**: (secure password)

### 2. Create Regular Users

Option A: Via Django Admin
```
1. Go to: http://localhost:8000/admin/
2. Login with your admin credentials
3. Click "Users" → "Add User"
4. Fill in username and password
5. Set permissions as needed
```

Option B: Via Python Shell
```bash
python manage.py shell
```

```python
from users.models import User

# Create a user
user = User.objects.create_user(
    username='john',
    email='john@bijouterie.local',
    password='securepass123',
    first_name='John',
    last_name='Doe'
)

# Grant permissions
from django.contrib.auth.models import Permission
user.user_permissions.add(
    Permission.objects.get(codename='view_user'),
    Permission.objects.get(codename='change_user')
)

exit()
```

### 3. Start Development Server

```bash
python manage.py runserver
```

### 4. Access the Application

- **Login Page**: http://localhost:8000/login/
- **Dashboard**: http://localhost:8000/ (auto-redirects to login if not authenticated)
- **Admin Panel**: http://localhost:8000/admin/

---

## 📍 URL Routes

### Authentication
| Route | Purpose | Auth Required |
|-------|---------|----------------|
| `/login/` | User login | No |
| `/logout/` | User logout | Yes |
| `/` | Main dashboard | Yes |

### User Profile (Personal)
| Route | Purpose | Auth Required |
|-------|---------|----------------|
| `/users/profile/` | View profile | Yes |
| `/users/profile/edit/` | Edit profile | Yes |
| `/users/profile/password/` | Change password | Yes |
| `/users/activity/` | Personal activity log | Yes |

### Admin - User Management
| Route | Purpose | Auth + Permission |
|-------|---------|-------------------|
| `/users/list/` | List all users | Yes + view_user |
| `/users/<id>/` | View user details | Yes + view_user |
| `/users/<id>/edit/` | Edit user | Yes + change_user |
| `/users/<id>/deactivate/` | Deactivate user | Yes + delete_user |
| `/users/activity/admin/` | All activity logs | Yes + view_activitylog |

---

## 🔑 Features

### 1. Login System
- Username/password authentication
- Session management
- "Remember me" option
- Next URL redirect support
- Activity logging on login/logout

### 2. User Profile
- View personal information
- Edit profile details (name, email)
- View activity statistics
- 7-day activity summary
- Last login timestamp

### 3. Password Management
- Change password securely
- Password validation
- Session maintained after change
- Activity logging

### 4. Activity Logging
**Personal Activity Log:**
- Login/Logout history
- Create/Update/Delete events
- Filtering by action type
- Date range filtering
- IP address tracking

**Admin Activity Logs:**
- View all system activities
- Search by user or action
- Statistics dashboard
- Comprehensive audit trail

### 5. Admin User Management
- List all users
- Search and filter users
- View user statistics
- Edit user information
- Activate/Deactivate users
- View user activity history

---

## 🛡️ Security Features

1. **Password Hashing**: Django's PBKDF2 algorithm
2. **Session Security**: HttpOnly cookies
3. **CSRF Protection**: CSRF token validation
4. **IP Tracking**: All activities logged with IP
5. **Permission-Based Access**: Role-based authorization
6. **Audit Trail**: Complete activity logging
7. **Inactive User Support**: Deactivation without deletion

---

## 📊 Activity Log Actions

The system tracks the following actions:

| Action | Display | When Triggered |
|--------|---------|-----------------|
| `login` | Connexion | User logs in |
| `logout` | Déconnexion | User logs out |
| `create` | Création | New resource created |
| `update` | Modification | Resource updated |
| `delete` | Suppression | Resource deleted |
| `view` | Consultation | Resource viewed |
| `print` | Impression | Document printed |
| `export` | Export | Data exported |
| `approve` | Approbation | Item approved |
| `reject` | Rejet | Item rejected |

---

## 👥 User Roles & Permissions

### Admin User
```
✓ Create/Read/Update/Delete users
✓ View activity logs (all)
✓ Manage permissions
✓ Access Django admin
```

### Regular User
```
✓ View own profile
✓ Edit own profile
✓ Change own password
✓ View own activity log
✗ Manage other users
```

---

## 🔍 Testing Login

### Test Credentials
After creating a superuser, you can immediately test:

1. **Navigate to**: http://localhost:8000/login/
2. **Enter credentials**: username and password from createsuperuser
3. **Click "Login"**
4. **Redirect**: Should redirect to dashboard (/)

### Test User Management (Admin Only)
1. Navigate to: http://localhost:8000/users/list/
2. View all users in the system
3. Click on a user to see details
4. Edit user information if permitted
5. View activity history

---

## 📝 System Files

### Views (users/views.py)
- `profile_view()` - View personal profile
- `profile_edit()` - Edit profile
- `password_change()` - Change password
- `activity_log()` - Personal activity history
- `user_list()` - Admin: List users
- `user_detail()` - Admin: View user details
- `user_edit()` - Admin: Edit user
- `user_deactivate()` - Admin: Deactivate user
- `activity_log_admin()` - Admin: View all activities

### Templates (templates/users/)
- `profile.html` - Profile view
- `profile_edit.html` - Profile edit form
- `password_change.html` - Password change form
- `activity_log.html` - Personal activity log
- `user_list.html` - Admin user list
- `user_detail.html` - Admin user details
- `user_edit.html` - Admin user edit
- `user_deactivate.html` - Admin deactivation
- `activity_log_admin.html` - Admin activity log

### Configuration (users/urls.py)
10 URL routes for authentication and user management

---

## 🐛 Troubleshooting

### "Invalid credentials" on login
- Verify username is correct (case-sensitive)
- Reset password via Django admin
- Check user is_active = True

### Can't access /users/list/
- User doesn't have `view_user` permission
- Grant permission in Django admin: Users → Select user → Permissions

### Activity not showing
- Check user has permission `view_activitylog`
- Activity only shows for logged-in user's actions

### Password change not working
- User must provide correct current password
- Passwords don't match (check caps lock)
- Session will be maintained after successful change

---

## 📋 Next Steps

1. **Create first admin user** using `createsuperuser`
2. **Access Django admin** at `/admin/` to manage permissions
3. **Test login** with created credentials
4. **Configure additional users** as needed
5. **Set up permissions** for different roles

---

## ✨ System Status

```
✅ Login system: READY
✅ User management: READY
✅ Activity logging: READY
✅ Permission system: READY
✅ Admin interface: READY
✅ Django checks: PASSING

Ready for production deployment!
```

---

**Last Updated**: 2026-02-04
**Version**: 1.0
**Status**: Production Ready
