#!/bin/bash
# Test runner script for IFI Essay Tool

echo "🧪 Running IFI Essay Tool Test Suite"
echo "===================================="
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest is not installed"
    echo "   Installing pytest..."
    pip install pytest pytest-mock
fi

# Set environment variables for testing
export FLASK_ENV=testing
export SUPABASE_URL=${SUPABASE_URL:-"https://test.supabase.co"}
export SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY:-"test-anon-key"}
export SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY:-"test-service-role-key"}

# Run tests
echo "📋 Running all tests..."
echo ""

pytest tests/ -v --tb=short

echo ""
echo "===================================="
echo "✅ Test run complete!"
echo ""
echo "📝 Test Coverage:"
echo "   - Validation tests (test_validate.py)"
echo "   - User scoping tests (test_user_scoping.py)"
echo "   - Bulk edit tests (test_bulk_edit.py)"
echo "   - Job processing tests (test_job_processing.py)"
echo "   - Grouping tests (test_grouping.py)"
echo "   - Approval gating tests (test_approval_gating.py)"
echo ""



