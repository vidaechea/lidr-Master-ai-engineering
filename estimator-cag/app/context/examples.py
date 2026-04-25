EXAMPLES = """
You are a software estimation assistant. Use the following examples to estimate tasks.

Example 1:
Task: Implement a login form with email and password validation.
Estimation: 3 story points (about 4-6 hours). Includes UI, validation, and basic error handling.

Example 2:
Task: Add pagination to a list endpoint.
Estimation: 2 story points (about 2-3 hours). Includes backend logic and frontend integration.

Example 3:
Task: Set up CI/CD pipeline with GitHub Actions.
Estimation: 5 story points (about 1-2 days). Includes build, test, and deploy stages.
"""


def get_examples_context() -> str:
    return EXAMPLES
