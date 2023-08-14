import os
from django.test import TestCase
from django.db import connections
from test_queries import NumQueriesMixin


class TestNumQueriesMixin(NumQueriesMixin, TestCase):

    def test_basic_functionality(self):
        with self.assertNumQueries(1):
            connections['default'].cursor().execute('SELECT 1')

    def test_file_creation(self):
        # This test checks if the SQL log file is created
        # You might need to adjust the expected filename based on your implementation
        expected_filename = 'path_to_expected_file.sqllog'  # Adjust this
        with self.assertNumQueries(1):
            connections['default'].cursor().execute('SELECT 1')
        self.assertTrue(os.path.exists(expected_filename))

    def test_file_comparison(self):
        # This test checks if the SQL log files are compared correctly
        # You might need to adjust the expected filename and contents based on your implementation
        expected_filename = 'path_to_expected_file.sqllog'  # Adjust this
        with open(expected_filename, 'w') as f:
            f.write('SELECT 1')
        with self.assertNumQueries(1):
            connections['default'].cursor().execute('SELECT 1')

    def test_environment_variables(self):
        os.environ['TEST_QUERIES_DISABLE'] = '1'
        with self.assertNumQueries(1):
            connections['default'].cursor().execute('SELECT 1')
        # Test content of the SQL log files
        with open('tests/sqllog/test_num_queries.TestNumQueriesMixin.test_environment_variables.0.sqllog.new', 'r') as f:
            self.assertEqual(f.read(), 'SELECT 1\n')

    def test_file_comparison_with_existing_lines(self):
        # This test checks if the SQL log files are compared correctly when the file already has lines
        # You might need to adjust the expected filename and contents based on your implementation
        expected_filename = 'tests/sqllog/test_num_queries.TestNumQueriesMixin.test_file_comparison_with_existing_lines.0.sqllog'
        with open(expected_filename, 'w') as f:
            f.write('SELECT 1\nSELECT 2')  # Writing multiple lines to the file
        with self.assertNumQueries(2):
            connections['default'].cursor().execute('SELECT 1')
            connections['default'].cursor().execute('SELECT 2')
        # Test content of the SQL log files
        with open('tests/sqllog/test_num_queries.TestNumQueriesMixin.test_file_comparison_with_existing_lines.0.sqllog.new', 'r') as f:
            self.assertEqual(f.read(), 'SELECT 1\nSELECT 2\n')

    def test_file_comparison_with_existing_lines_not_equal(self):
        expected_filename = 'tests/sqllog/test_num_queries.TestNumQueriesMixin.test_file_comparison_with_existing_lines.0.sqllog'
        with open(expected_filename, 'w') as f:
            f.write('SELECT 1')  # Writing multiple lines to the file
        with self.assertRaisesRegex(AssertionError, 'Captured queries were:\n1. SELECT 1\n2. SELECT 2'):
            with self.assertNumQueries(1):
                connections['default'].cursor().execute('SELECT 1')
                connections['default'].cursor().execute('SELECT 2')
