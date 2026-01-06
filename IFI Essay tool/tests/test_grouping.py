"""
Unit tests for grouping module.
"""

import unittest
from pipeline.grouping import group_records, normalize_key, get_school_grade_records


class TestGrouping(unittest.TestCase):
    
    def test_normalize_key(self):
        """Test key normalization."""
        # Test trimming
        self.assertEqual(normalize_key("  School Name  "), "school name")
        
        # Test collapsing spaces
        self.assertEqual(normalize_key("School    Name"), "school name")
        
        # Test case folding
        self.assertEqual(normalize_key("SCHOOL NAME"), "school name")
        self.assertEqual(normalize_key("School Name"), "school name")
        
        # Test empty/None
        self.assertEqual(normalize_key(""), "")
        self.assertEqual(normalize_key(None), "")
    
    def test_group_records_needs_review(self):
        """Test that records missing school/grade go to needs_review."""
        records = [
            {"submission_id": "1", "school_name": None, "grade": None, "needs_review": False},
            {"submission_id": "2", "school_name": "", "grade": "5", "needs_review": False},
            {"submission_id": "3", "school_name": "School A", "grade": None, "needs_review": False},
            {"submission_id": "4", "school_name": "School A", "grade": "5", "needs_review": True},
        ]
        
        grouped = group_records(records)
        
        # All should be in needs_review
        self.assertEqual(len(grouped["needs_review"]), 4)
        self.assertEqual(len(grouped["schools"]), 0)
    
    def test_group_records_by_school_grade(self):
        """Test grouping by school and grade."""
        records = [
            {"submission_id": "1", "school_name": "School A", "grade": "5", "needs_review": False, "student_name": "Student 1"},
            {"submission_id": "2", "school_name": "School A", "grade": "5", "needs_review": False, "student_name": "Student 2"},
            {"submission_id": "3", "school_name": "School A", "grade": "6", "needs_review": False, "student_name": "Student 3"},
            {"submission_id": "4", "school_name": "School B", "grade": "5", "needs_review": False, "student_name": "Student 4"},
        ]
        
        grouped = group_records(records)
        
        # None should be in needs_review
        self.assertEqual(len(grouped["needs_review"]), 0)
        
        # Check schools structure
        self.assertIn("School A", grouped["schools"])
        self.assertIn("School B", grouped["schools"])
        
        # Check grades
        self.assertIn("5", grouped["schools"]["School A"])
        self.assertIn("6", grouped["schools"]["School A"])
        self.assertIn("5", grouped["schools"]["School B"])
        
        # Check record counts
        self.assertEqual(len(grouped["schools"]["School A"]["5"]), 2)
        self.assertEqual(len(grouped["schools"]["School A"]["6"]), 1)
        self.assertEqual(len(grouped["schools"]["School B"]["5"]), 1)
    
    def test_group_records_mixed(self):
        """Test mixed records (some approved, some need review)."""
        records = [
            {"submission_id": "1", "school_name": "School A", "grade": "5", "needs_review": False, "student_name": "Student 1"},
            {"submission_id": "2", "school_name": None, "grade": "5", "needs_review": False, "student_name": "Student 2"},
            {"submission_id": "3", "school_name": "School A", "grade": "6", "needs_review": False, "student_name": "Student 3"},
            {"submission_id": "4", "school_name": "School A", "grade": "5", "needs_review": True, "student_name": "Student 4"},
        ]
        
        grouped = group_records(records)
        
        # Records 2 and 4 should be in needs_review
        self.assertEqual(len(grouped["needs_review"]), 2)
        needs_review_ids = {r["submission_id"] for r in grouped["needs_review"]}
        self.assertIn("2", needs_review_ids)
        self.assertIn("4", needs_review_ids)
        
        # Records 1 and 3 should be in schools
        self.assertEqual(len(grouped["schools"]["School A"]["5"]), 1)
        self.assertEqual(len(grouped["schools"]["School A"]["6"]), 1)
    
    def test_group_records_case_insensitive(self):
        """Test that grouping is case-insensitive."""
        records = [
            {"submission_id": "1", "school_name": "School A", "grade": "5", "needs_review": False, "student_name": "Student 1"},
            {"submission_id": "2", "school_name": "SCHOOL A", "grade": "5", "needs_review": False, "student_name": "Student 2"},
            {"submission_id": "3", "school_name": "school a", "grade": "5", "needs_review": False, "student_name": "Student 3"},
        ]
        
        grouped = group_records(records)
        
        # All should be grouped under "School A" (first occurrence's display value)
        self.assertEqual(len(grouped["schools"]), 1)
        self.assertIn("School A", grouped["schools"])
        self.assertEqual(len(grouped["schools"]["School A"]["5"]), 3)
    
    def test_group_records_whitespace_normalization(self):
        """Test that whitespace is normalized for grouping."""
        records = [
            {"submission_id": "1", "school_name": "School A", "grade": "5", "needs_review": False, "student_name": "Student 1"},
            {"submission_id": "2", "school_name": "School  A", "grade": "5", "needs_review": False, "student_name": "Student 2"},
            {"submission_id": "3", "school_name": "  School A  ", "grade": "5", "needs_review": False, "student_name": "Student 3"},
        ]
        
        grouped = group_records(records)
        
        # All should be grouped together
        self.assertEqual(len(grouped["schools"]), 1)
        self.assertEqual(len(grouped["schools"]["School A"]["5"]), 3)


if __name__ == "__main__":
    unittest.main()

