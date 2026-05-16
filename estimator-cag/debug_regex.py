import re

_PROJECT_NAME_PATTERNS = [
    re.compile(
        r"(?i:(?:project|app|application|platform|system|tool|service)\s+"
        r"(?:called|named|titled|known as)\s+)['\"]?([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)(?=\s+(?:for|that|to|in|on|at)\b|['\"]|$|\.)"
    ),
    re.compile(r"(?i:building)\s+['\"]?([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)(?=\s+(?:for|that|to|in|on|at)\b|['\"]|$|\.)['\"]?"),
    re.compile(r"^#+\s+(.+)$", re.MULTILINE),  # first Markdown heading
    re.compile(
        r"(?i:project[:\s]+)['\"]?([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)(?=\s+(?:for|that|to|in|on|at)\b|['\"]|$|\.)"
    ),
]

text = "We are building an app called ShopEasy for our client."

print(f"Text: {text}\n")

# Test full patterns
for i, pattern in enumerate(_PROJECT_NAME_PATTERNS):
    match = pattern.search(text)
    if match:
        print(f"Pattern {i}:")
        print(f"  Full match: '{match.group(0)}'")
        print(f"  Captured group 1: '{match.group(1)}'")
        print()
        break
else:
    print("No pattern matched")

# Also test with quotes
print("\n--- Test with 'DataPipeline Pro' ---")
text2 = 'The project named "DataPipeline Pro" will process logs.'
for i, pattern in enumerate(_PROJECT_NAME_PATTERNS):
    match = pattern.search(text2)
    if match:
        print(f"Pattern {i}:")
        print(f"  Full match: '{match.group(0)}'")
        print(f"  Captured group 1: '{match.group(1)}'")
        print()
        break

# Test with simple name
print("\n--- Test with 'Invoice' ---")
text3 = 'We are building a project called Invoice.'
for i, pattern in enumerate(_PROJECT_NAME_PATTERNS):
    match = pattern.search(text3)
    if match:
        print(f"Pattern {i}:")
        print(f"  Full match: '{match.group(0)}'")
        print(f"  Captured group 1: '{match.group(1)}'")
        print()
        break



