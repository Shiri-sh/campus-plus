---
name: pytest-unittesting
description: Rules and guidelines for writing high-quality, atomic unit tests using pytest for the Scribe project. Use when writing or refactoring unit tests, adding pytest coverage, working in test_*.py files, or when the user asks for unit tests in config.py, jira_client.py, or security.py.
---

# Pytest Writing Guidelines

You are an expert Python QA Engineer. When writing or refactoring unit tests for this project, you must strictly follow these structural and architectural rules.

## 1. Test Atomicity & Flow
- **No Conditional Logic:** Never use `if`, `else`, `for`, or `while` loops inside a test body. If a test has multiple paths, split it into separate, isolated test functions.
- **Single Responsibility:** Each test must validate exactly one behavior, one specific state, or one expected exception.
- **AAA Pattern:** Maintain clear visual separation inside the test using line breaks:
  - **Arrange:** Set up mocks, environment variables, and fixtures.
  - **Act:** Execute the single function being tested.
  - **Assert:** Verify the outcome with explicit `assert` statements.

## 2. Test Parameterization (Data-Driven Testing)
- Do not duplicate test logic to test multiple inputs. Use `@pytest.mark.parametrize` to inject test data matrices.
- Define clear variable names in the parametrization decorator and map them cleanly to the test function arguments.

## 3. Mocking & Network Isolation
- **No Live Network Calls:** The suite must run offline. Always mock external integrations (`issues.redhat.com` Jira API endpoints and GCP Vertex AI Gemini SDK responses).
- Use `monkeypatch` to isolate environment variables (`.env`) or configuration components, ensuring local secrets never leak into active execution memory during tests.

## 4. Codecov Target Execution
- Focus on covering edge cases, target failure paths (`try/except` exceptions, status code errors like 400/401/500 from Jira), and input validations to achieve meaningful coverage on `config.py`, `jira_client.py`, and `security.py`.
