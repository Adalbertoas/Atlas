"""Calculadora segura: evalúa expresiones matemáticas sin usar eval().

Solo números, operadores aritméticos y funciones de una lista blanca. Los
exponentes y resultados enormes se rechazan para que "9**9**9" no congele
el backend.
"""
from __future__ import annotations

import ast
import math
import operator

MAX_EXPONENT = 1000
MAX_MAGNITUDE = 1e100
MAX_LENGTH = 300

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_FUNCTIONS = {
    "sqrt": math.sqrt, "raiz": math.sqrt, "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
    "abs": abs, "round": round, "redondear": round, "floor": math.floor, "ceil": math.ceil,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "sen": math.sin,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "log": math.log, "ln": math.log, "log10": math.log10, "log2": math.log2, "exp": math.exp,
    "factorial": math.factorial, "radians": math.radians, "degrees": math.degrees,
    "min": min, "max": max,
}  # fmt: skip
_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


class CalculatorError(ValueError):
    """Expresión inválida; el mensaje es apto para el usuario."""


def _check(value: float) -> float:
    if isinstance(value, (int, float)) and abs(value) > MAX_MAGNITUDE:
        raise CalculatorError("El resultado es demasiado grande.")
    return value


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise CalculatorError("El exponente es demasiado grande.")
        try:
            return _check(_BINARY[type(node.op)](left, right))
        except ZeroDivisionError as exc:
            raise CalculatorError("División por cero.") from exc
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS and not node.keywords:
        args = [_eval(arg) for arg in node.args]
        if node.func.id == "factorial" and (args and args[0] > 500):
            raise CalculatorError("El factorial es demasiado grande.")
        try:
            return _check(_FUNCTIONS[node.func.id](*args))
        except (ValueError, TypeError, OverflowError) as exc:
            raise CalculatorError(f"No se puede calcular {node.func.id} con esos valores.") from exc
    raise CalculatorError("La expresión tiene algo que no es una operación matemática.")


def calculate(expression: str) -> float:
    text = expression.strip()
    if not text:
        raise CalculatorError("Falta la expresión.")
    if len(text) > MAX_LENGTH:
        raise CalculatorError("La expresión es demasiado larga.")
    # Notación habitual: "×" para multiplicar, "^" para potencia, "÷" para dividir.
    text = text.replace("×", "*").replace("÷", "/").replace("^", "**")
    # "15% de 200" o "15 % de 200" -> 0.15 * 200
    text = text.replace("% de", "/100*").replace("%de", "/100*")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError("No entiendo la expresión.") from exc
    try:
        result = _eval(tree)
    except OverflowError as exc:
        raise CalculatorError("El resultado es demasiado grande.") from exc
    if isinstance(result, float) and result.is_integer() and abs(result) < 1e15:
        return int(result)
    return result


def format_number(value: float) -> str:
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    return f"{value:,.10g}".replace(",", " ")
