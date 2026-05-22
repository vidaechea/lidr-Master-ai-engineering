"""Anthropic API - Tool Use (Function Calling) Example."""

import os
import json
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()


class AnthropicToolUseClient:
    """Client demonstrating Anthropic Tool Use / Function Calling."""

    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found")
        self.client = Anthropic(api_key=api_key)

    # Simulated tool functions
    def get_weather(self, city: str, unit: str = "celsius") -> Dict[str, Any]:
        """Simulated weather API."""
        weather_data = {
            "Madrid": {"temp": 28, "condition": "Soleado", "humidity": 45},
            "Barcelona": {"temp": 25, "condition": "Parcialmente nublado", "humidity": 60},
            "New York": {"temp": 22, "condition": "Nublado", "humidity": 65},
        }
        city_key = next((k for k in weather_data if k.lower() == city.lower()), None)
        if city_key:
            data = weather_data[city_key]
            temp = data["temp"] if unit == "celsius" else int(data["temp"] * 9/5 + 32)
            return {
                "city": city_key,
                "temperature": temp,
                "unit": unit,
                "condition": data["condition"],
                "humidity": data["humidity"]
            }
        return {"error": f"City {city} not found"}

    def calculate_mortgage(self, principal: float, annual_rate: float, years: int) -> Dict[str, Any]:
        """Calculate monthly mortgage payment."""
        monthly_rate = annual_rate / 100 / 12
        num_payments = years * 12
        if monthly_rate == 0:
            monthly_payment = principal / num_payments
        else:
            monthly_payment = principal * (monthly_rate * (1 + monthly_rate) ** num_payments) / \
                            ((1 + monthly_rate) ** num_payments - 1)
        
        return {
            "principal": principal,
            "annual_rate": annual_rate,
            "years": years,
            "monthly_payment": round(monthly_payment, 2),
            "total_paid": round(monthly_payment * num_payments, 2),
            "total_interest": round(monthly_payment * num_payments - principal, 2)
        }

    def get_stock_price(self, symbol: str) -> Dict[str, Any]:
        """Simulated stock price lookup."""
        stocks = {
            "AAPL": 195.50,
            "GOOGL": 142.30,
            "MSFT": 380.25,
            "TESLA": 248.60,
            "ANTHROPIC": 999.99,  # Hypothetical
        }
        symbol = symbol.upper()
        if symbol in stocks:
            return {"symbol": symbol, "price": stocks[symbol]}
        return {"error": f"Stock {symbol} not found"}

    def define_tools(self) -> list:
        """Define all available tools for Claude."""
        return [
            {
                "name": "get_weather",
                "description": "Obtiene el clima actual de una ciudad. Retorna temperatura, condición y humedad.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "Nombre de la ciudad (ej: Madrid, Barcelona, New York)"
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Unidad de temperatura",
                            "default": "celsius"
                        }
                    },
                    "required": ["city"]
                }
            },
            {
                "name": "calculate_mortgage",
                "description": "Calcula el pago mensual de una hipoteca y el total de intereses.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "principal": {
                            "type": "number",
                            "description": "Monto principal del préstamo en dólares"
                        },
                        "annual_rate": {
                            "type": "number",
                            "description": "Tasa de interés anual en porcentaje (ej: 4.5)"
                        },
                        "years": {
                            "type": "integer",
                            "description": "Plazo del préstamo en años"
                        }
                    },
                    "required": ["principal", "annual_rate", "years"]
                }
            },
            {
                "name": "get_stock_price",
                "description": "Obtiene el precio actual de una acción.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Símbolo de la acción (ej: AAPL, GOOGL, MSFT)"
                        }
                    },
                    "required": ["symbol"]
                }
            }
        ]

    def process_tool_call(self, tool_name: str, tool_input: Dict) -> str:
        """Execute the appropriate tool based on name."""
        if tool_name == "get_weather":
            result = self.get_weather(**tool_input)
        elif tool_name == "calculate_mortgage":
            result = self.calculate_mortgage(**tool_input)
        elif tool_name == "get_stock_price":
            result = self.get_stock_price(**tool_input)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
        
        return json.dumps(result)

    def chat_with_tools(self, user_message: str) -> str:
        """Chat with tool use enabled."""
        tools = self.define_tools()
        
        messages = [{"role": "user", "content": user_message}]
        
        print(f"\n📝 Usuario: {user_message}")
        print("=" * 70)
        
        # First request - model may call tools
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            tools=tools,
            messages=messages,
            temperature=0.3
        )
        
        # Process tool calls if any
        while response.stop_reason == "tool_use":
            # Add assistant's response
            messages.append({"role": "assistant", "content": response.content})
            
            # Extract and process tool calls
            tool_results = []
            for content in response.content:
                if hasattr(content, 'type') and content.type == "tool_use":
                    tool_name = content.name
                    tool_input = content.input
                    
                    print(f"🔧 Herramienta: {tool_name}")
                    print(f"   Inputs: {json.dumps(tool_input, indent=2)}")
                    
                    # Execute tool
                    result = self.process_tool_call(tool_name, tool_input)
                    print(f"   Resultado: {result}\n")
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": content.id,
                        "content": result
                    })
            
            # Add tool results and continue
            messages.append({"role": "user", "content": tool_results})
            
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                tools=tools,
                messages=messages,
                temperature=0.3
            )
        
        # Extract final text response
        final_response = ""
        for content in response.content:
            if hasattr(content, 'text'):
                final_response = content.text
        
        print(f"💬 Respuesta Claude:\n{final_response}")
        return final_response


if __name__ == "__main__":
    client = AnthropicToolUseClient()
    
    print("=" * 70)
    print("ANTHROPIC TOOL USE (FUNCTION CALLING) - DEMO")
    print("=" * 70)
    
    # Example 1: Weather check
    client.chat_with_tools("¿Cuál es el clima en Madrid ahora? ¿Y en Barcelona?")
    
    print("\n" + "=" * 70)
    
    # Example 2: Mortgage calculation
    client.chat_with_tools("Calcula el pago mensual de una hipoteca de $300,000 al 4.5% anual durante 30 años")
    
    print("\n" + "=" * 70)
    
    # Example 3: Stock prices
    client.chat_with_tools("¿Cuál es el precio actual de AAPL, GOOGL y TESLA?")
    
    print("\n" + "=" * 70)
    
    # Example 4: Combined request
    client.chat_with_tools(
        "Estoy considerando mudarme a Barcelona. "
        "¿Cuál es el clima? "
        "Si obtengo una hipoteca de $250,000 al 4.2% para 25 años, "
        "¿cuánto sería el pago mensual?"
    )
