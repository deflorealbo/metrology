"""Анализ метрик Джилба для исходного кода Ruby.

Принятые правила подсчёта:
- CL = количество if/unless/elsif и тернарных условий
       + циклы (включая each do / each { })
       + сумма количества when для каждого case;
- default/else не считается дополнительным условием;
- CLI возвращает номер самого глубокого уровня при нумерации с нуля;
  case с n операторами when добавляет max(0, n - 1) уровней при замене
  на цепочку вложенных if;
- N — число вхождений перечисленных категорий операторов.
- Имена вызываемых методов/функций, переменные, литералы и скобки не считаются.
- В отдельном окне выводятся категория, обозначение оператора и число вхождений.

Это лёгкий лексико-структурный анализатор, а не полноценная реализация
грамматики Ruby. Для необычных метапрограммных конструкций Ruby подсчёт N
может потребовать уточнения правил под конкретную методичку.
"""

from __future__ import annotations

import re
import tkinter as tk
from collections import Counter
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------
# Лексический анализ Ruby
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*[!?]?")
NUMBER_RE = re.compile(r"(?:\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)")
SYMBOL_RE = re.compile(r":[A-Za-z_][A-Za-z0-9_]*[!?]?")

MULTI_OPERATORS = sorted(
    [
        "<=>", "===", "**=", "<<=", ">>=", "&&=", "||=", "...",
        "<=>", "<=" , ">=", "==", "!=", "+=", "-=", "*=", "/=", "%=",
        "**", "<<", ">>", "&&", "||", "::", "=>", "->", "=~", "!~",
        "..", "&.", "&=", "|=", "^=", "\n",
    ],
    key=len,
    reverse=True,
)

SINGLE_OPERATOR_CHARS = set("+-*/%<>=!&|^~?")

CONTROL_BLOCK_WORDS = {
    "if", "unless", "case", "while", "until", "for",
    "def", "class", "module", "begin", "loop",
}
MODIFIER_WORDS = {"if", "unless", "while", "until"}
IGNORED_BLOCK_WORDS = {"end", "else", "elsif", "when", "then", "rescue", "ensure", "in", "do"}

CONTROL_OPERATOR_WORDS = {
    "if", "unless", "elsif", "case", "while", "until", "for",
    "def", "class", "module", "begin", "rescue", "ensure",
    "return", "yield", "break", "next", "redo", "retry", "super",
    "raise", "throw", "catch", "and", "or", "not", "loop",
}

BUILTIN_CALLS = {
    "puts", "print", "printf", "sprintf", "format", "gets", "readline",
    "require", "require_relative", "include", "extend", "raise", "fail",
    "p", "pp", "exit", "abort", "sleep", "rand", "srand", "system",
    "exec", "spawn", "load", "open", "lambda", "proc", "attr_reader",
    "attr_writer", "attr_accessor", "defined?",
}

# Методы, которые обычно перечисляют элементы/повторяют блок.
ITERATOR_METHODS = {
    "each", "each_with_index", "each_with_object", "each_key", "each_value",
    "each_pair", "times", "upto", "downto", "step", "map", "collect",
    "map!", "select", "reject", "find_all", "filter", "filter_map",
    "reduce", "inject", "cycle", "reverse_each", "each_slice", "each_cons",
}

SYMBOLIC_OPERATORS = {
    "<=>", "===", "==", "!=", "<", ">", "<=", ">=", "=~", "!~",
    "=", "+=", "-=", "*=", "/=", "%=", "**=", "<<=", ">>=", "&&=", "||=",
    "+", "-", "*", "/", "%", "**", "<<", ">>", "&&", "||", "!", "&", "|",
    "^", "~", "::", "=>", "->", "..", "...", "&=", "|=", "^=",
}


def tokenize(source: str) -> List[Token]:
    """Токенизирует Ruby-код, пропуская комментарии и содержимое строк."""
    tokens: List[Token] = []
    i = 0
    line = 1
    col = 1
    n = len(source)

    def advance(text: str) -> None:
        nonlocal line, col
        newlines = text.count("\n")
        if newlines:
            line += newlines
            col = len(text.rsplit("\n", 1)[-1]) + 1
        else:
            col += len(text)

    while i < n:
        ch = source[i]

        # Ruby block comments =begin ... =end должны начинаться с начала строки.
        if ch == "=" and (i == 0 or source[i - 1] == "\n") and source.startswith("=begin", i):
            end_pos = source.find("=end", i + 6)
            if end_pos == -1:
                advance(source[i:])
                break
            end_line = source.find("\n", end_pos + 4)
            if end_line == -1:
                advance(source[i:])
                break
            skipped = source[i:end_line + 1]
            advance(skipped)
            i = end_line + 1
            continue

        if ch in " \t\r":
            advance(ch)
            i += 1
            continue

        if ch == "\n":
            tokens.append(Token("NEWLINE", "\n", line, col))
            advance(ch)
            i += 1
            continue

        if ch == "#":
            end = source.find("\n", i)
            if end == -1:
                advance(source[i:])
                break
            advance(source[i:end])
            i = end
            continue

        # Строки и символьные литералы не должны порождать ложные if/case.
        if ch in ('"', "'", "`"):
            quote = ch
            start_line, start_col = line, col
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == quote:
                    j += 1
                    break
                j += 1
            raw = source[i:j]
            tokens.append(Token("STRING", raw, start_line, start_col))
            advance(raw)
            i = j
            continue

        # Символы вида :items — литералы, не ключевые слова.
        if ch == ":":
            sym_match = SYMBOL_RE.match(source, i)
            if sym_match:
                raw = sym_match.group(0)
                tokens.append(Token("SYMBOL", raw, line, col))
                advance(raw)
                i = sym_match.end()
                continue

        number_match = NUMBER_RE.match(source, i)
        if number_match:
            raw = number_match.group(0)
            tokens.append(Token("NUMBER", raw, line, col))
            advance(raw)
            i = number_match.end()
            continue

        ident_match = IDENT_RE.match(source, i)
        if ident_match:
            raw = ident_match.group(0)
            tokens.append(Token("IDENT", raw, line, col))
            advance(raw)
            i = ident_match.end()
            continue

        matched_operator = None
        for op in MULTI_OPERATORS:
            if op != "\n" and source.startswith(op, i):
                matched_operator = op
                break

        if matched_operator:
            tokens.append(Token("OP", matched_operator, line, col))
            advance(matched_operator)
            i += len(matched_operator)
            continue

        if ch in SINGLE_OPERATOR_CHARS:
            tokens.append(Token("OP", ch, line, col))
            advance(ch)
            i += 1
            continue

        tokens.append(Token("PUNCT", ch, line, col))
        advance(ch)
        i += 1

    return tokens


def significant_tokens(tokens: List[Token]) -> List[Token]:
    return [t for t in tokens if t.kind != "NEWLINE"]


def previous_significant(tokens: List[Token], index: int) -> Optional[Tuple[int, Token]]:
    j = index - 1
    while j >= 0:
        if tokens[j].kind != "NEWLINE":
            return j, tokens[j]
        j -= 1
    return None


def next_significant(tokens: List[Token], index: int) -> Optional[Tuple[int, Token]]:
    j = index + 1
    while j < len(tokens):
        if tokens[j].kind != "NEWLINE":
            return j, tokens[j]
        j += 1
    return None


def is_modifier(tokens: List[Token], index: int) -> bool:
    """Определяет постфиксные формы: action if condition / action while condition."""
    if tokens[index].kind != "IDENT" or tokens[index].value not in MODIFIER_WORDS:
        return False
    prev = previous_significant(tokens, index)
    if prev is None:
        return False
    _, token = prev
    if token.line != tokens[index].line:
        return False
    if token.kind == "IDENT" and token.value in {
        "if", "unless", "while", "until", "elsif", "else", "then", "do", "when", "end",
    }:
        return False
    # Модификатор следует после завершённого выражения, но не после знака,
    # который требует выражение справа (например, x = if condition).
    if token.kind in {"NUMBER", "STRING", "SYMBOL"}:
        return True
    if token.kind == "IDENT":
        return token.value not in {"def", "class", "module", "return", "yield"}
    if token.kind == "PUNCT" and token.value in {")", "]", "}",
    }:
        return True
    return False


def _is_iterator_method_before(tokens: List[Token], index: int) -> bool:
    prev = previous_significant(tokens, index)
    if prev is None:
        return False
    j, token = prev
    if token.kind != "IDENT" or token.value not in ITERATOR_METHODS:
        return False
    before_method = previous_significant(tokens, j)
    # Обычный метод-итератор обычно вызывается через точку, либо как 5.times.
    if before_method and before_method[1].value in {".", "&."}:
        return True
    # Допускаем и вызов вида each do ... end.
    return token.value in {"each", "times", "loop"}


def _loop_do_is_attached_to_keyword(tokens: List[Token], index: int) -> bool:
    """True для `while cond do`, `for x in xs do` и `loop do`.

    В этих формах цикл уже открыл блок; do не должен добавлять второй.
    """
    current_line = tokens[index].line
    j = index - 1
    while j >= 0:
        token = tokens[j]
        if token.line != current_line:
            break
        if token.kind == "IDENT" and token.value in {"while", "until", "for", "loop"}:
            if token.value in MODIFIER_WORDS and is_modifier(tokens, j):
                j -= 1
                continue
            return True
        if token.value == ";":
            break
        j -= 1
    return False


def _is_iterator_brace(tokens: List[Token], index: int) -> bool:
    return _is_iterator_method_before(tokens, index)


# ---------------------------------------------------------------------
# Сбор информации о case / блоках
# ---------------------------------------------------------------------

def case_when_counts(tokens: List[Token]) -> Dict[int, int]:
    """Возвращает {индекс токена case: количество when в этом case}.

    Стек нужен, чтобы when вложенного case не попал в счётчик внешнего case.
    """
    stack: List[dict] = []
    results: Dict[int, int] = {}

    for index, token in enumerate(tokens):
        if token.kind == "IDENT":
            val = token.value

            if val == "case":
                stack.append({"kind": "case", "index": index, "when_count": 0, "levels": 0})
                continue

            if val in {"if", "unless", "while", "until", "for"}:
                if not is_modifier(tokens, index):
                    stack.append({"kind": val, "levels": 0})
                continue

            if val == "loop":
                stack.append({"kind": "loop", "levels": 0})
                continue

            if val == "do":
                if _loop_do_is_attached_to_keyword(tokens, index):
                    continue
                kind = "iter_block" if _is_iterator_method_before(tokens, index) else "do"
                stack.append({"kind": kind, "levels": 0})
                continue

            if val in {"def", "class", "module", "begin"}:
                stack.append({"kind": val, "levels": 0})
                continue

            if val == "when":
                for frame in reversed(stack):
                    if frame["kind"] == "case":
                        frame["when_count"] += 1
                        break
                continue

            if val == "end" and stack:
                frame = stack.pop()
                if frame["kind"] == "case":
                    results[frame["index"]] = frame["when_count"]

        elif token.kind == "PUNCT" and token.value == "{":
            if _is_iterator_brace(tokens, index):
                stack.append({"kind": "iter_block", "levels": 0})
        elif token.kind == "PUNCT" and token.value == "}":
            if stack and stack[-1]["kind"] == "iter_block":
                stack.pop()

    # На случай синтаксически неполного фрагмента (например, код выделен из метода).
    for frame in stack:
        if frame["kind"] == "case":
            results[frame["index"]] = frame["when_count"]
    return results


def count_iterator_blocks(tokens: List[Token]) -> int:
    count = 0
    for i, token in enumerate(tokens):
        if token.kind == "IDENT" and token.value == "do":
            if not _loop_do_is_attached_to_keyword(tokens, i) and _is_iterator_method_before(tokens, i):
                count += 1
        elif token.kind == "PUNCT" and token.value == "{" and _is_iterator_brace(tokens, i):
            count += 1
    return count


# ---------------------------------------------------------------------
# Метрики потока управления
# ---------------------------------------------------------------------

def control_flow_metrics(tokens: List[Token]) -> dict:
    cases = case_when_counts(tokens)
    branch_counts = Counter()
    loop_counts = Counter()

    for i, token in enumerate(tokens):
        if token.kind == "IDENT":
            val = token.value
            if val in {"if", "unless", "elsif"}:
                branch_counts[val] += 1
            elif val in {"while", "until", "for"}:
                loop_counts[val] += 1
            elif val == "loop":
                loop_counts["loop"] += 1
        elif token.kind == "OP" and token.value == "?":
            # Тернарный оператор. Методы empty? / is_a? — цельные IDENT-токены.
            branch_counts["тернарный ? :"] += 1

    case_contribution = sum(n for n in cases.values())
    non_case_branch_total = sum(branch_counts.values())
    iterator_count = count_iterator_blocks(tokens)
    if iterator_count:
        loop_counts["each/итератор"] += iterator_count

    branch_total = non_case_branch_total + case_contribution
    loop_total = sum(loop_counts.values())
    CL = branch_total + loop_total
    CLI = calculate_cli(tokens, cases)

    return {
        "branch_counts": dict(branch_counts),
        "loop_counts": dict(loop_counts),
        "case_when_counts": list(cases.values()),
        "case_contribution": case_contribution,
        "branch_total": branch_total,
        "loop_total": loop_total,
        "CL": CL,
        "CLI": CLI,
    }


def calculate_cli(tokens: List[Token], cases: Optional[Dict[int, int]] = None) -> int:
    """Возвращает номер самого глубокого уровня при нумерации с нуля.

    Внутри расчёта depth хранится количество одновременно активных уровней.
    Для case с n операторами when модель цепочки проверок добавляет n уровней.
    В конце единица вычитается для преобразования количества уровней в номер.
    """
    if cases is None:
        cases = case_when_counts(tokens)

    stack: List[dict] = []
    depth = 0
    max_depth = 0

    for i, token in enumerate(tokens):
        if token.kind == "IDENT":
            val = token.value

            if val in {"if", "unless"}:
                if is_modifier(tokens, i):
                    max_depth = max(max_depth, depth + 1)
                else:
                    stack.append({"kind": val, "levels": 1})
                    depth += 1
                    max_depth = max(max_depth, depth)
                continue

            if val == "elsif":
                if stack and stack[-1]["kind"] in {"if", "unless"}:
                    stack[-1]["levels"] += 1
                    depth += 1
                    max_depth = max(max_depth, depth)
                else:
                    max_depth = max(max_depth, depth + 1)
                continue

            if val == "case":
                when_count = cases.get(i, 0)
                # Каждый when представлен отдельной проверкой.
                # Ветка default/else не создаёт проверки, но код внутри неё
                # расположен после цепочки проверок when.
                levels = when_count
                stack.append({"kind": "case", "levels": levels})
                depth += levels
                max_depth = max(max_depth, depth)
                continue

            if val in {"while", "until", "for"}:
                if is_modifier(tokens, i):
                    max_depth = max(max_depth, depth + 1)
                else:
                    stack.append({"kind": val, "levels": 1})
                    depth += 1
                    max_depth = max(max_depth, depth)
                continue

            if val == "loop":
                stack.append({"kind": "loop", "levels": 1})
                depth += 1
                max_depth = max(max_depth, depth)
                continue

            if val == "do":
                if _loop_do_is_attached_to_keyword(tokens, i):
                    continue
                if _is_iterator_method_before(tokens, i):
                    stack.append({"kind": "iter_block", "levels": 1})
                    depth += 1
                    max_depth = max(max_depth, depth)
                else:
                    stack.append({"kind": "do", "levels": 0})
                continue

            if val in {"def", "class", "module", "begin"}:
                stack.append({"kind": val, "levels": 0})
                continue

            if val == "end" and stack:
                frame = stack.pop()
                depth -= frame.get("levels", 0)
                if depth < 0:
                    depth = 0
                continue

        elif token.kind == "PUNCT":
            if token.value == "{" and _is_iterator_brace(tokens, i):
                stack.append({"kind": "iter_block", "levels": 1})
                depth += 1
                max_depth = max(max_depth, depth)
            elif token.value == "}" and stack and stack[-1]["kind"] == "iter_block":
                frame = stack.pop()
                depth -= frame.get("levels", 0)
                if depth < 0:
                    depth = 0

        elif token.kind == "OP" and token.value == "?":
            max_depth = max(max_depth, depth + 1)

    # По принятому здесь правилу CLI — это номер самого глубокого уровня,
    # а нумерация начинается с нуля. Поэтому глубина в 6 активных конструкций
    # соответствует CLI = 5. Если управляющих конструкций нет, возвращаем 0.
    return max(0, max_depth - 1)


# ---------------------------------------------------------------------
# Подсчёт операторов N по категориям, заданным для этой работы
# ---------------------------------------------------------------------

ASSIGNMENT_OPERATORS = {
    "=", "+=", "-=", "*=", "/=", "%=", "**=", "<<=", ">>=",
    "&&=", "||=", "&=", "|=", "^=",
}

COMPARISON_OPERATORS = {"==", "!=", "<", ">", "<=", ">=", "<=>", "===", "=~", "!~"}
ARITHMETIC_OPERATORS = {"+", "-", "*", "/", "%", "**"}
LOGICAL_OPERATORS = {"&&", "||", "and", "or"}
UNARY_OPERATORS = {"!", "~", "not"}
RANGE_OPERATORS = {"..", "..."}
RETURN_OPERATORS = {"return", "break", "next", "redo", "retry", "throw"}
CONDITIONAL_OPERATORS = {"if", "unless", "elsif", "when"}
LOOP_OPERATORS = {"while", "until", "for", "loop"}

# Ключевые слова, после которых обычно ожидается выражение.
_PREFIX_CONTEXT_KEYWORDS = {
    "return", "break", "next", "when", "then", "else", "do", "in",
    "if", "unless", "elsif", "while", "until", "case", "and", "or", "not",
    "yield", "rescue",
}


def _is_unary_position(tokens: List[Token], index: int) -> bool:
    """Эвристически отличает унарные +, -, * и & от бинарных."""
    prev = previous_significant(tokens, index)
    if prev is None:
        return True

    _, token = prev
    if token.kind == "OP":
        # После другого оператора обычно требуется операнд: a * -b.
        return token.value not in {"++", "--"}

    if token.kind == "PUNCT":
        return token.value in {"(", "[", "{", ",", ";", ":"}

    if token.kind == "IDENT" and token.value in _PREFIX_CONTEXT_KEYWORDS:
        return True

    return False


def extract_operators(tokens: List[Token]) -> List[Tuple[str, str]]:
    """Возвращает пары (категория, обозначение оператора).

    Не учитывает имена вызываемых методов/функций, операнды и разделительную
    пунктуацию. Список категорий задан пользователем: арифметика, сравнения,
    логика, присваивания, унарные, диапазоны, тернарный оператор, defined?, ::,
    ветвления, циклы и операторы возврата/передачи управления.
    """
    operators: List[Tuple[str, str]] = []

    for i, token in enumerate(tokens):
        if token.kind == "IDENT":
            val = token.value

            if val == "puts":
                operators.append(("Вывод данных", "puts"))
            elif val == "defined?":
                operators.append(("defined?", val))
            elif val in CONDITIONAL_OPERATORS:
                display = "case..when" if val == "when" else val
                operators.append(("Условия и ветвления", display))
            elif val in LOOP_OPERATORS:
                operators.append(("Циклы", val))
            elif val in RETURN_OPERATORS:
                operators.append(("Возврат/передача управления", val))
            elif val in LOGICAL_OPERATORS:
                operators.append(("Логические", val))
            elif val == "not":
                operators.append(("Унарные", val))
            elif val == "def":
                # Считаем ключевое слово объявления, но не имя метода после него.
                operators.append(("Объявление метода", val))
            elif val == "do":
                # Имя итератора each/times не считается; считаем сам блок цикла.
                if (not _loop_do_is_attached_to_keyword(tokens, i)
                        and _is_iterator_method_before(tokens, i)):
                    operators.append(("Циклы", "each"))

        elif token.kind == "OP":
            val = token.value

            if val in ASSIGNMENT_OPERATORS:
                operators.append(("Присваивания", val))
            elif val in RANGE_OPERATORS:
                operators.append(("Диапазоны", val))
            elif val == "::":
                operators.append(("Область имён", val))
            elif val == "?":
                operators.append(("Тернарный", "?:"))
            elif val in COMPARISON_OPERATORS:
                operators.append(("Сравнения", val))
            elif val in LOGICAL_OPERATORS:
                operators.append(("Логические", val))
            elif val in UNARY_OPERATORS:
                operators.append(("Унарные", val))
            elif val in ARITHMETIC_OPERATORS:
                if val in {"+", "-", "*"} and _is_unary_position(tokens, i):
                    operators.append(("Унарные", "унарный " + val))
                else:
                    operators.append(("Арифметические", val))
            elif val == "&" and _is_unary_position(tokens, i):
                # Унарный &: передача блока/Proc в аргументе метода.
                operators.append(("Унарные", "унарный &"))

        elif token.kind == "PUNCT" and token.value == "{":
            # Считаем блок-итератор как цикл, но не имя метода перед ним.
            if _is_iterator_brace(tokens, i):
                operators.append(("Циклы", "each"))

    return operators


def jilb_metrics(source: str) -> dict:
    tokens = tokenize(source)
    control = control_flow_metrics(tokens)
    operator_occurrences = extract_operators(tokens)
    op_freq = Counter(operator_occurrences)
    N = len(operator_occurrences)
    CL = control["CL"]

    # Строки для отдельного окна: категория, обозначение оператора, количество.
    operator_rows = [
        {"category": category, "operator": operator, "count": count}
        for (category, operator), count in sorted(
            op_freq.items(), key=lambda item: (item[0][0].casefold(), item[0][1].casefold())
        )
    ]

    return {
        "operators": dict(op_freq),
        "operator_rows": operator_rows,
        "N": N,
        "branch_counts": control["branch_counts"],
        "loop_counts": control["loop_counts"],
        "case_when_counts": control["case_when_counts"],
        "case_contribution": control["case_contribution"],
        "branch_total": control["branch_total"],
        "loop_total": control["loop_total"],
        "CL": CL,
        "cl": (CL / N) if N else 0.0,
        "CLI": control["CLI"],
    }


# ---------------------------------------------------------------------
# Графический интерфейс Tkinter
# ---------------------------------------------------------------------

class JilbApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Задание 2а")
        root.geometry("1050x720")
        root.minsize(820, 560)

        # Панель кнопок управления.
        toolbar = ttk.Frame(root, padding=(8, 8, 8, 4))
        toolbar.pack(fill=tk.X)

        ttk.Button(
            toolbar,
            text="Открыть файл Ruby...",
            command=self.open_file,
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            toolbar,
            text="Анализировать",
            command=self.analyze,
        ).pack(side=tk.LEFT, padx=6)

        ttk.Button(
            toolbar,
            text="Очистить",
            command=self.clear,
        ).pack(side=tk.LEFT, padx=6)

        self.operators_button = ttk.Button(
            toolbar,
            text="Найденные операторы...",
            command=self.show_operators,
            state=tk.DISABLED,
        )
        self.operators_button.pack(side=tk.LEFT, padx=6)
        self.operator_rows = []
        self.operator_window = None
        self.operator_tree = None
        self.operator_total_var = tk.StringVar(value="Найдено операторов: —")

        # Основная область: редактор кода и компактная панель четырёх метрик.
        content = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        editor_frame = ttk.Frame(content, padding=4)
        content.add(editor_frame, weight=4)

        ttk.Label(editor_frame, text="Исходный код Ruby:").pack(anchor=tk.W, pady=(0, 5))

        editor_container = ttk.Frame(editor_frame)
        editor_container.pack(fill=tk.BOTH, expand=True)

        self.code_text = tk.Text(
            editor_container,
            wrap=tk.NONE,
            font=("Consolas", 10),
            undo=True,
            padx=6,
            pady=6,
        )
        yscroll = ttk.Scrollbar(editor_container, orient=tk.VERTICAL, command=self.code_text.yview)
        xscroll = ttk.Scrollbar(editor_frame, orient=tk.HORIZONTAL, command=self.code_text.xview)
        self.code_text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.code_text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        editor_container.rowconfigure(0, weight=1)
        editor_container.columnconfigure(0, weight=1)
        xscroll.pack(fill=tk.X)

        metrics_frame = ttk.LabelFrame(content, text="Результаты", padding=12)
        content.add(metrics_frame, weight=1)

        self.metric_vars = {
            "N": tk.StringVar(value="—"),
            "CL": tk.StringVar(value="—"),
            "cl": tk.StringVar(value="—"),
            "CLI": tk.StringVar(value="—"),
        }

        metric_descriptions = {
            "N": "Количество операторов (N)",
            "CL": "Абсолютная сложность (CL)",
            "cl": "Относительная сложность (cl)",
            "CLI": "Максимальный уровень (CLI, с 0)",
        }

        for row, key in enumerate(("N", "CL", "cl", "CLI")):
            ttk.Label(
                metrics_frame,
                text=metric_descriptions[key],
                wraplength=190,
                justify=tk.LEFT,
            ).grid(row=row * 2, column=0, sticky="w", pady=(8 if row else 0, 2))

            ttk.Label(
                metrics_frame,
                textvariable=self.metric_vars[key],
                font=("Consolas", 14, "bold"),
            ).grid(row=row * 2 + 1, column=0, sticky="w", pady=(0, 8))

        metrics_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(
            root,
            text="Готово",
            anchor=tk.W,
            relief=tk.SUNKEN,
            padding=4,
        )
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM)

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл Ruby",
            filetypes=[("Ruby files", "*.rb"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                content = file.read()
        except OSError as exc:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{exc}")
            return

        self.code_text.delete("1.0", tk.END)
        self.code_text.insert("1.0", content)
        self.status_label.config(text=f"Загружен файл: {path}")
        self.reset_metrics()

    def reset_metrics(self) -> None:
        for variable in self.metric_vars.values():
            variable.set("—")
        self.operator_rows = []
        self.operators_button.config(state=tk.DISABLED)
        self.operator_total_var.set("Найдено операторов: —")
        if self.operator_tree is not None and self.operator_tree.winfo_exists():
            for item in self.operator_tree.get_children():
                self.operator_tree.delete(item)

    def clear(self) -> None:
        self.code_text.delete("1.0", tk.END)
        self.reset_metrics()
        self.status_label.config(text="Поле очищено")

    def show_operators(self) -> None:
        if not self.operator_rows:
            messagebox.showinfo("Операторы", "Сначала проанализируйте Ruby-код.")
            return

        if self.operator_window is not None and self.operator_window.winfo_exists():
            self.operator_window.deiconify()
            self.operator_window.lift()
            self._refresh_operator_table()
            return

        self.operator_window = tk.Toplevel(self.root)
        self.operator_window.title("Найденные операторы Ruby")
        self.operator_window.geometry("660x520")
        self.operator_window.minsize(520, 360)

        outer = ttk.Frame(self.operator_window, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            outer,
            textvariable=self.operator_total_var,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W, pady=(0, 8))

        columns = ("category", "operator", "count")
        table_frame = ttk.Frame(outer)
        table_frame.pack(fill=tk.BOTH, expand=True)

        self.operator_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=18,
        )
        self.operator_tree.heading("category", text="Категория")
        self.operator_tree.heading("operator", text="Оператор")
        self.operator_tree.heading("count", text="Количество")
        self.operator_tree.column("category", width=235, anchor=tk.W)
        self.operator_tree.column("operator", width=190, anchor=tk.W)
        self.operator_tree.column("count", width=100, anchor=tk.CENTER)

        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.operator_tree.yview)
        self.operator_tree.configure(yscrollcommand=yscroll.set)
        self.operator_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Button(outer, text="Закрыть", command=self.operator_window.destroy).pack(
            anchor=tk.E, pady=(8, 0)
        )
        self._refresh_operator_table()

    def _refresh_operator_table(self) -> None:
        if self.operator_tree is None or not self.operator_tree.winfo_exists():
            return
        for item in self.operator_tree.get_children():
            self.operator_tree.delete(item)
        for row in self.operator_rows:
            self.operator_tree.insert(
                "", tk.END,
                values=(row["category"], row["operator"], row["count"]),
            )
        self.operator_total_var.set(f"Найдено операторов: {sum(row['count'] for row in self.operator_rows)}")

    def analyze(self) -> None:
        source = self.code_text.get("1.0", "end-1c")
        if not source.strip():
            messagebox.showwarning("Внимание", "Введите или загрузите код Ruby.")
            return

        try:
            metrics = jilb_metrics(source)
        except Exception as exc:
            messagebox.showerror("Ошибка анализа", str(exc))
            return

        self.metric_vars["N"].set(str(metrics["N"]))
        self.metric_vars["CL"].set(str(metrics["CL"]))
        self.metric_vars["cl"].set(f"{metrics['cl']:.4f}")
        self.metric_vars["CLI"].set(str(metrics["CLI"]))
        self.operator_rows = metrics["operator_rows"]
        self.operators_button.config(state=tk.NORMAL)
        self.operator_total_var.set(f"Найдено операторов: {metrics['N']}")
        if self.operator_tree is not None and self.operator_tree.winfo_exists():
            self._refresh_operator_table()
        self.status_label.config(text="Анализ завершён")




if __name__ == "__main__":
    
    root = tk.Tk()
    app = JilbApp(root)
    root.mainloop()
