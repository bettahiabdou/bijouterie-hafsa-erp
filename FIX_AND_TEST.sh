#!/bin/bash

echo "========================================"
echo "🔧 RESETTING DJANGO AND CLEARING CACHE"
echo "========================================"

# Stop any running Django server (Ctrl+C)
echo "1. Stop your Django server if it's running (press Ctrl+C in the terminal)"
echo ""

# Pull latest code
echo "2. Pulling latest code..."
cd /Users/user/.claude-worktrees/Claude_cde/serene-gagarin
git pull origin main

# Run migrations
echo "3. Running database migrations..."
python3 manage.py migrate sales

# Start fresh Django server
echo ""
echo "4. Starting Django server..."
echo "Run this command in your terminal:"
echo ""
echo "   cd /Users/user/.claude-worktrees/Claude_cde/serene-gagarin"
echo "   python3 manage.py runserver"
echo ""

# Browser instructions
echo "========================================"
echo "🌐 BROWSER STEPS"
echo "========================================"
echo ""
echo "5. Hard refresh your browser:"
echo "   - Windows/Linux: Ctrl+Shift+R"
echo "   - Mac: Cmd+Shift+R"
echo ""
echo "6. Clear browser cache completely:"
echo "   - Windows/Linux: Ctrl+Shift+Delete"
echo "   - Mac: Command+Shift+Delete"
echo ""
echo "7. Visit: http://127.0.0.1:8000/sales/invoices/create/"
echo ""
echo "8. Open browser console (F12) and check for:"
echo "   ✓ Article management elements found"
echo "   ✓ Main form found"
echo ""
echo "9. Test the buttons - they should now work!"
echo ""
