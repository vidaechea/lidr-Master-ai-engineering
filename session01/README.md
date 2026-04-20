# Session 01: API Clients for OpenAI and Anthropic

Clean, reusable Python clients for OpenAI and Anthropic APIs with support for both Google Colab and local development.

## Features

- 🚀 Simple, minimal API clients (OpenAI & Anthropic)
- 💰 Cost tracking for API calls
- 📊 Multiple models supported for each provider
- 🔧 Works with both Google Colab and local Python
- 📦 Environment variable management with `.env`
- 🔄 Consistent interface across both providers

## Supported Models

### OpenAI Models

| Model | Input Price | Output Price | Use Case |
|-------|-------------|--------------|----------|
| `gpt-3.5-turbo` | $0.50/1M | $1.50/1M | Budget-friendly, fast |
| `gpt-4o-mini` | $0.15/1M | $0.60/1M | **Default** - Best price/performance |
| `gpt-4-turbo` | $10.00/1M | $30.00/1M | High accuracy, complex tasks |

### Anthropic Claude Models

| Model | Input Price | Output Price | Use Case |
|-------|-------------|--------------|----------|
| `claude-haiku-4-5-20251001` | $0.80/1M | $4.00/1M | **Default** - Budget-friendly, fast |
| `claude-sonnet-4-6` | $3.00/1M | $15.00/1M | Balanced performance & cost |
| `claude-opus-4-7` | $15.00/1M | $75.00/1M | Maximum capability |

## Setup

### Prerequisites

- Python 3.8+
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys)) **OR**
- Anthropic API key ([Get one here](https://console.anthropic.com))

### Local Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd lidr-Master-ai-engineering
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure API keys**
   Create a `.env` file in the project root:
   ```env
   OPENAI_API_KEY=sk-proj-your-openai-key-here
   ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
   ```

## Usage

### Option 1: OpenAI Client (Local Python)

#### Basic Usage

```python
from session01.session_01_1_api_openai_client import OpenAIClient

# Initialize client (loads API key from .env)
client = OpenAIClient()

# Make a query
result = client.query(
    message="What are the benefits of cloud migration?",
    instructions="Be concise and technical."
)

# Check for errors
if "error" in result:
    print(f"Error: {result['error']}")
else:
    print(result["content"])
    print(f"Cost: ${result['cost_usd']:.6f}")
```

#### Using Different Models

```python
# Use GPT-3.5 Turbo (cheaper)
result = client.query(
    message="Your question here",
    model="gpt-3.5-turbo"
)

# Use GPT-4 Turbo (more capable)
result = client.query(
    message="Complex analysis task",
    model="gpt-4-turbo"
)
```

#### Available Parameters

```python
result = client.query(
    message="Your question",           # Required
    instructions="System instructions", # Optional
    model="gpt-4o-mini",              # Optional, default: gpt-4o-mini
    temperature=0.3,                  # Optional, range: 0-1 (default: 0.3)
    max_tokens=1000                   # Optional (default: 1000)
)
```

#### Response Structure

```python
{
    "content": "The response text",
    "model": "gpt-4o-mini",
    "id": "resp_xxx",
    "input_tokens": 10,
    "output_tokens": 50,
    "cost_usd": 0.000015
}
```

#### Running the Client Directly

```bash
source .venv/bin/activate
python session01/session_01_1_api_openai_client.py
```

---

### Option 2: Anthropic Client (Local Python)

#### Basic Usage

```python
from session01.session_01_2_api_anthropic_client import AnthropicClient

# Initialize client (loads API key from .env)
client = AnthropicClient()

# Make a query
result = client.query(
    message="What are the benefits of cloud migration?",
    instructions="Be concise and technical."
)

# Check for errors
if "error" in result:
    print(f"Error: {result['error']}")
else:
    print(result["content"])
    print(f"Cost: ${result['cost_usd']:.6f}")
```

#### Using Different Models

```python
# Use Claude Haiku (cheapest)
result = client.query(
    message="Your question here",
    model="claude-haiku-4-5-20251001"
)

# Use Claude Sonnet (balanced)
result = client.query(
    message="Your question here",
    model="claude-sonnet-4-6"
)

# Use Claude Opus (most capable)
result = client.query(
    message="Complex analysis task",
    model="claude-opus-4-7"
)
```

#### Response Structure

```python
{
    "content": "The response text",
    "model": "claude-haiku-4-5-20251001",
    "id": "msg_xxx",
    "input_tokens": 10,
    "output_tokens": 50,
    "stop_reason": "end_turn",
    "cost_usd": 0.000038
}
```

#### Running the Client Directly

```bash
source .venv/bin/activate
python session01/session_01_2_api_anthropic_client.py
```

---

### Option 3: Google Colab Notebook

#### Quick Start - OpenAI

Click here to open OpenAI notebook in Colab:
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/vidaechea/lidr-Master-ai-engineering/blob/development/session01/session_01_1_api_openai.ipynb)

#### Quick Start - Anthropic

Click here to open Anthropic notebook in Colab:
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/vidaechea/lidr-Master-ai-engineering/blob/development/session01/session_01_2_api_anthropic.ipynb)

#### Setup in Colab

1. **Add API keys to Colab Secrets**
   - Click 🔑 "Secrets" in the left sidebar
   - Click "+ Add new secret"
   - For OpenAI: Name: `OPENAI_API_KEY` | Value: Your OpenAI API key
   - For Anthropic: Name: `ANTHROPIC_API_KEY` | Value: Your Anthropic API key
   - Click Save for each

2. **Install dependencies** (in first cell)
   ```python
   !pip install -q python-dotenv openai anthropic
   ```

3. **Load API keys** (in second cell)
   ```python
   from google.colab import userdata
   import os
   
   OPENAI_API_KEY = userdata.get('OPENAI_API_KEY')
   os.environ['OPENAI_API_KEY'] = OPENAI_API_KEY
   
   ANTHROPIC_API_KEY = userdata.get('ANTHROPIC_API_KEY')
   os.environ['ANTHROPIC_API_KEY'] = ANTHROPIC_API_KEY
   ```

4. **Use the client** (OpenAI)
   ```python
   from session01.session_01_1_api_openai_client import OpenAIClient
   
   client = OpenAIClient()
   result = client.query("Your question here")
   print(result["content"])
   ```

#### Example: Complete Colab Workflow (OpenAI)

```python
# Cell 1: Install packages
!pip install -q python-dotenv openai anthropic

# Cell 2: Load secrets
from google.colab import userdata
import os

OPENAI_API_KEY = userdata.get('OPENAI_API_KEY')
os.environ['OPENAI_API_KEY'] = OPENAI_API_KEY

ANTHROPIC_API_KEY = userdata.get('ANTHROPIC_API_KEY')
os.environ['ANTHROPIC_API_KEY'] = ANTHROPIC_API_KEY

# Cell 3: Use OpenAI client
from session01.session_01_1_api_openai_client import OpenAIClient

client = OpenAIClient()
result = client.query(
    message="Estimate: PostgreSQL to Aurora migration timeline",
    instructions="You are a cloud architect. Be specific about phases.",
    model="gpt-4o-mini"
)

print(result["content"])
print(f"\n💰 Cost: ${result['cost_usd']:.6f}")
```

#### Example: Complete Colab Workflow (Anthropic)

```python
# Cell 1: Install packages
!pip install -q python-dotenv openai anthropic

# Cell 2: Load secrets
from google.colab import userdata
import os

ANTHROPIC_API_KEY = userdata.get('ANTHROPIC_API_KEY')
os.environ['ANTHROPIC_API_KEY'] = ANTHROPIC_API_KEY

# Cell 3: Use Anthropic client
from session01.session_01_2_api_anthropic_client import AnthropicClient

client = AnthropicClient()
result = client.query(
    message="Estimate: PostgreSQL to Aurora migration timeline",
    instructions="You are a cloud architect. Be specific about phases.",
    model="claude-haiku-4-5-20251001"
)

print(result["content"])
print(f"\n💰 Cost: ${result['cost_usd']:.6f}")
print(f"Stop reason: {result['stop_reason']}")
```

---

## Project Structure

```
session01/
├── README.md                                      # This file
├── session_01_1_api_openai_client.py             # OpenAI client class
├── session_01_1_api_openai.ipynb                 # OpenAI Colab notebook
├── session_01_2_api_anthropic_client.py          # Anthropic client class
└── session_01_2_api_anthropic.ipynb              # Anthropic Colab notebook
```

## Environment Variables

### Local (.env file)
```env
OPENAI_API_KEY=sk-proj-your-openai-key-here
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
```

### Colab (Secrets)
- Name: `OPENAI_API_KEY` | Value: Your OpenAI API key
- Name: `ANTHROPIC_API_KEY` | Value: Your Anthropic API key

## Troubleshooting

### "API_KEY not found" (OpenAI or Anthropic)
- **Local**: Check `.env` file exists and has correct key
- **Colab**: Verify secret is added correctly (🔑 icon)

### "Invalid or missing API key"
- **OpenAI**: Verify at [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **Anthropic**: Verify at [console.anthropic.com](https://console.anthropic.com)
- Check for extra spaces or newlines in `.env`
- Try generating a new API key

### "Model not found" errors
- **OpenAI**: Check available models at [OpenAI Models](https://platform.openai.com/docs/models)
- **Anthropic**: Check available models at [Anthropic Docs](https://docs.anthropic.com/en/docs/resources/model-deprecations)
- Some models may be deprecated or retired

### Rate limiting errors
- Reduce `max_tokens` parameter
- Add delays between requests
- **OpenAI**: Check usage at [platform.openai.com/usage](https://platform.openai.com/usage)
- **Anthropic**: Check usage at [console.anthropic.com/usage](https://console.anthropic.com/usage)

## Examples

### Example 1: Cloud Architecture Analysis
```python
client = OpenAIClient()
result = client.query(
    message="Pros and cons of moving to serverless architecture",
    instructions="Provide a technical analysis with cost implications",
    model="gpt-4o-mini"
)
print(result["content"])
```

### Example 2: Code Review
```python
code_snippet = """
def calculate_total(items):
    total = 0
    for item in items:
        total = total + item['price'] * item['quantity']
    return total
"""

result = client.query(
    message=f"Review this code:\n{code_snippet}",
    instructions="Identify issues and suggest improvements",
    temperature=0.2  # Lower temperature for technical consistency
)
print(result["content"])
```

### Example 3: Budget-Conscious Batch Processing
```python
questions = [
    "What is cloud computing?",
    "Explain containerization",
    "What is CI/CD?"
]

total_cost = 0
for question in questions:
    result = client.query(
        message=question,
        model="gpt-3.5-turbo"  # Cheapest model
    )
    print(result["content"])
    total_cost += result["cost_usd"]

print(f"\nTotal batch cost: ${total_cost:.6f}")
```

## API Reference

### OpenAIClient

#### `__init__(api_key: Optional[str] = None)`
Initialize the client. If no API key is provided, loads from environment.

#### `query(message, instructions=None, model=None, temperature=0.3, max_tokens=1000)`
Send a query to OpenAI.

**Parameters:**
- `message` (str): The user message
- `instructions` (str, optional): System instructions for the model
- `model` (str, optional): Model name. Defaults to `DEFAULT_MODEL`
- `temperature` (float): Sampling temperature (0-1). Default: 0.3
- `max_tokens` (int): Max output tokens. Default: 1000

**Returns:** Dict with response data or error

---

### AnthropicClient

#### `__init__(api_key: Optional[str] = None)`
Initialize the client. If no API key is provided, loads from environment.

#### `query(message, instructions=None, model=None, temperature=0.3, max_tokens=1000)`
Send a query to Anthropic Claude.

**Parameters:**
- `message` (str): The user message
- `instructions` (str, optional): System instructions for the model
- `model` (str, optional): Model name. Defaults to `DEFAULT_MODEL`
- `temperature` (float): Sampling temperature (0-1). Default: 0.3
- `max_tokens` (int): Max output tokens. Default: 1000

**Returns:** Dict with response data or error (includes `stop_reason` field)

## License

MIT

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. **OpenAI**: Review [OpenAI's documentation](https://platform.openai.com/docs)
3. **Anthropic**: Review [Anthropic's documentation](https://docs.anthropic.com)
4. Open an issue in the repository
