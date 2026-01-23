"""
Unit tests for QueryAnalyzer.
"""

import pytest
from rail_django.debugging.query_analyzer.analyzer import QueryAnalyzer
from rail_django.debugging.query_analyzer.types import QueryIssueType, QuerySeverity

pytestmark = pytest.mark.unit

class TestQueryAnalyzer:
    @pytest.fixture
    def schema_string(self):
        return """
        type User {
            id: ID!
            username: String!
            email: String!
            posts: [Post!]!
        }
        
        type Post {
            id: ID!
            title: String!
            content: String!
            author: User!
            comments: [Comment!]!
        }
        
        type Comment {
            id: ID!
            text: String!
            author: User!
        }
        
        type Query {
            users: [User!]!
            user(id: ID!): User
            posts: [Post!]!
        }
        """

    @pytest.fixture
    def analyzer(self, schema_string):
        return QueryAnalyzer(
            schema_string=schema_string,
            max_complexity=100,
            max_depth=5,
            field_complexity_map={"posts": 15, "comments": 20}
        )

    def test_analyze_simple_query(self, analyzer):
        query = "{ users { username } }"
        result = analyzer.analyze_query(query)
        
        assert result.is_valid is True
        assert result.complexity.total_score > 0
        assert result.complexity.field_count == 2 # users + username
        assert len(result.issues) == 0

    def test_detect_expensive_fields(self, analyzer):
        query = "{ users { posts { title } } }"
        result = analyzer.analyze_query(query)
        
        expensive_issues = [i for i in result.issues if i.issue_type == QueryIssueType.EXPENSIVE_FIELD]
        assert len(expensive_issues) > 0
        assert any("posts" in i.message for i in expensive_issues)

    def test_detect_deep_nesting(self, analyzer):
        # max_depth=5
        query = """
        {
          users {
            posts {
              comments {
                author {
                  posts {
                    title
                  }
                }
              }
            }
          }
        }
        """
        result = analyzer.analyze_query(query)
        
        depth_issues = [i for i in result.issues if i.issue_type == QueryIssueType.DEEP_NESTING]
        assert len(depth_issues) > 0
        assert result.complexity.max_depth > 5

    def test_detect_security_risks(self, analyzer):
        query = "{ __schema { types { name } } }"
        result = analyzer.analyze_query(query)
        
        security_issues = [i for i in result.issues if i.issue_type == QueryIssueType.SECURITY_RISK]
        assert len(security_issues) > 0
        assert any("Introspection" in i.message for i in security_issues)

    def test_calculate_scores(self, analyzer):
        query = "{ users { username } }"
        result = analyzer.analyze_query(query)
        
        assert result.security_score == 100.0
        assert result.performance_score > 90.0
        
        # Query with issues
        query_bad = "{ __schema { types { name } } }"
        result_bad = analyzer.analyze_query(query_bad)
        assert result_bad.security_score < 100.0

    def test_invalid_query_parsing(self, analyzer):
        query = "{ users { " # Unclosed
        result = analyzer.analyze_query(query)
        
        assert result.is_valid is False
        assert len(result.issues) > 0
        assert any(i.severity == QuerySeverity.CRITICAL for i in result.issues)
